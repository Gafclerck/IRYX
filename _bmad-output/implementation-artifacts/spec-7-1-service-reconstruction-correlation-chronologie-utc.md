---
title: "Story 7.1 : Service de reconstruction et de corrélation de la chronologie unifiée UTC (FR24)"
type: 'feature'
created: '2026-11-25'
status: 'done'
baseline_commit: '198be26a619c34f03d50a396fd1684decee3a6ab'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-7-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Lors d'une investigation numérique DFIR, les artefacts forensiques sont extraits d'outils hétérogènes (EVTX, logs texte/web, registre Windows, Prefetch, mémoire vive), rendant impossible la reconstruction linéaire de l'attaque sans une corrélation chronologique unifiée ordonnée en temps universel (UTC) et strictement garantie contre toute altération ou fabrication artificielle (Invariant 2).

**Approach:** Concevoir et implémenter `TimelineService` dans le package `iryx.analytics`, un service de projection déterministe en lecture pure sans table mutable, agrégeant et ordonnant en UTC strictement croissant les entités `Observation` d'un dossier avec jointure sur les `Evidence` scellées sources, tout en isolant rigoureusement les faits non horodatés dans une partition dédiée.

## Boundaries & Constraints

**Always:**
- Respect absolu de l'Invariant 2 : la chronologie est une vue/projection calculée dynamiquement à la volée. Aucune table de persistance mutable d'événements temporels (`timeline_events`) ne doit exister ni être modifiée.
- Ordonnancement chronologique strictement croissant en UTC (`timestamp_utc ASC NULLS LAST`, départagé de façon déterministe par `Observation.id ASC`) pour tous les événements horodatés.
- Tout événement de timeline doit comporter : `timestamp_utc` (timezone-aware UTC), `observation_id`, `tool_name`, `evidence_id`, `evidence_name` (nom du fichier scellé d'origine ou `None`), `summary` (résumé textuel synthétique du fait technique), `source_location` et `details` (`normalized_content`).
- Toute observation dont l'horodatage est nul (`timestamp_utc is None`) doit être isolée dans la section dédiée `undated_events` (« Faits non horodatés ») sans fausser ni interrompre l'ordre chronologique de la timeline principale.
- Cloisonnement strict multi-tenant : toute requête SQL filtre obligatoirement par `case_id`.
- Déterminisme et performance : zéro appel LLM dans le service de timeline.

**Never:**
- Ne jamais implémenter de méthode d'insertion, d'édition ou de suppression manuelle d'événements temporels (interdiction absolue de forger des entrées temporelles).
- Ne jamais masquer ou ignorer silencieusement des observations : les observations sans timestamp doivent obligatoirement être restituées dans `undated_events`.
- Ne jamais stocker de timestamps "naïfs" sans fuseau horaire : la normalisation UTC doit être explicite.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Nominal multi-sources | Dossier avec N observations horodatées (EVTX, Apache, Prefetch) reliées à des preuves | `TimelineProjectionResponse` avec `events` ordonnés par `timestamp_utc` croissant, `evidence_name` résolus, résumés lisibles | N/A |
| Observations mixtes | Dossier comportant des observations avec et sans `timestamp_utc` | `events` contient exclusivement les faits horodatés triés ; `undated_events` contient les faits non horodatés | N/A |
| Dossier vide | `case_id` valide sans aucune observation | `events=[]`, `undated_events=[]`, `total_events=0`, `total_undated=0` | N/A |
| Observation sans preuve (`source_id=None`) | Observation issue d'un outil sans preuve directe liée | Événement inclus dans la timeline avec `evidence_id=None` et `evidence_name=None` | N/A |
| Résumé technique hétérogène | `normalized_content` varié (`summary`, `message`, `event_id`, ou structure imbriquée) | Extraction robuste d'un `summary` concis, sans exception | Fallback déterministe sur chaîne JSON ou texte brut tronqué |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/analytics/schemas.py` -- Définition des schémas Pydantic `TimelineEventOut`, `UndatedFactOut`, `TimelineProjectionResponse` avec sérialisation ISO-8601 UTC.
- `backend/src/iryx/analytics/services.py` -- Implémentation du service `TimelineService` avec `get_timeline_projection()` et fonction d'extraction synthétique `_extract_technical_summary()`.
- `backend/src/iryx/analytics/__init__.py` -- Exportation des nouveaux schémas et de la classe `TimelineService`.
- `backend/tests/unit/test_timeline_service.py` -- Suite de tests unitaires validant l'ordonnancement UTC, le cloisonnement des faits non horodatés, la résolution des preuves et l'Invariant 2.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/analytics/schemas.py` -- Définir les modèles Pydantic `TimelineEventOut`, `UndatedFactOut`, `TimelineProjectionResponse` -- Typage strict et validation de la projection de chronologie.
- [x] `backend/src/iryx/analytics/services.py` -- Implémenter la classe `TimelineService` avec `get_timeline_projection` et jointure `Evidence` -- Calcul déterministe de la timeline unifiée UTC et séparation des faits non horodatés (FR24, Invariant 2).
- [x] `backend/src/iryx/analytics/__init__.py` -- Exposer `TimelineService`, `TimelineEventOut`, `UndatedFactOut`, `TimelineProjectionResponse` -- Interface publique du package `analytics`.
- [x] `backend/tests/unit/test_timeline_service.py` -- Créer la suite de tests unitaires pour `TimelineService` -- Couverture complète des critères d'acceptation, du tri UTC, des observations non horodatées et de l'Invariant 2.

**Acceptance Criteria:**
- Given un dossier comportant des observations horodatées provenant de plusieurs sources (EVTX, Registre, Prefetch, logs réseau Volatility), when `TimelineService.get_timeline_projection(db, case_id)` est invoqué, then il agrège toutes les entités `Observation` disposant d'un `timestamp_utc` non nul, triées par ordre chronologique strictement croissant en UTC, avec chaque entrée contenant l'horodatage UTC, l'identifiant de l'observation source, le nom de l'outil générateur, le nom de la preuve scellée d'origine et le résumé du fait technique.
- Given des observations sans horodatage extractible (`timestamp_utc` nul), when la chronologie est générée, then ces observations sont isolées dans une section spécifique « Faits non horodatés » (`undated_events`) sans fausser l'ordre de la timeline principale.
- Given l'Invariant 2 du modèle de données (`docs/03`), when le service opère, then il n'existe aucune méthode ni point d'accès permettant d'insérer, d'éditer ou de forger manuellement un événement temporel dans la timeline (la timeline est une projection calculée pure).

## Implementation Notes

- Implémentation de `TimelineFactBase`, `TimelineEventOut`, `UndatedFactOut` et `TimelineProjectionResponse` dans `backend/src/iryx/analytics/schemas.py`.
- Implémentation du service `TimelineService` et de l'algorithme d'extraction de résumé technique `_extract_technical_summary` dans `backend/src/iryx/analytics/services.py`.
- Support des invocations de `TimelineService.get_timeline_projection` au niveau classe ou instance via un descripteur polymorphe `_TimelineProjectionDispatcher`.
- Strict respect de l'Invariant 2 : projection calculée déterministe en lecture pure sans aucune table mutable `timeline_events` et sans méthode de modification.
- Normalisation automatique des horodatages en timezone UTC (sensible au fuseau horaire) et séparation rigoureuse des faits non horodatés dans `undated_events`.
- Export de tous les schémas et du service dans `backend/src/iryx/analytics/__init__.py`.
- Couverture de tests unitaires exhaustive (19 tests) dans `backend/tests/unit/test_timeline_service.py` validant tous les cas nominaux, limites, d'isolation multi-tenant et de conformité Invariant 2.

## Spec Change Log

## Review Triage Log

| Emplacement | Constat du réviseur | Verdict | Justification / Décision |
|-------------|---------------------|---------|--------------------------|
| `backend/src/iryx/analytics/services.py:438` | Falsy zero pour `event_id: 0` dans l'extraction de résumé | `medium` | Réel : `0` est un EventID Windows valide. Patch appliqué avec `is not None`. |
| `backend/src/iryx/analytics/services.py:448` | Falsy zero pour `pid: 0` dans l'extraction de résumé | `medium` | Réel : PID 0 (System Idle Process). Patch appliqué avec `is not None`. |
| `backend/src/iryx/analytics/services.py:453` | Résumé vide retourné sur commande constituée d'espaces | `low` | Réel. Patch appliqué : validation de chaîne non vide après `.strip()`. |
| `backend/src/iryx/analytics/schemas.py:258` | Omission de `tool_execution_id` dans `TimelineFactBase` | `low` | Réel pour la traçabilité. Patch appliqué : champ optionnel ajouté et transmis. |
| `backend/src/iryx/analytics/services.py:567` | Absence de vérification d'existence du dossier (Case) | `false` | Réfutation : Conforme à la matrice I/O (projection vide pour dossier sans observation). L'erreur 404 est gérée par l'API (Story 7.2). |
| `backend/src/iryx/analytics/services.py:580` | Absence de pagination / streaming sur volumétries extrêmes | `defer` | Reporté dans `deferred-work.md` : objet explicite de la Story 7.2 (NFR-PERF-07). |
| `backend/src/iryx/analytics/services.py:586` | Remplacement des contenus non-dictionnaires par `{}` | `low` | Réel. Patch appliqué : encapsulation sécurisée dans `{"raw": obs.normalized_content}`. |
| `backend/src/iryx/analytics/__init__.py:43` | Export de fonction privée `_extract_technical_summary` dans `__all__` | `low` | Réel (PEP 8). Patch appliqué : retirée de `__all__`, seule `extract_technical_summary` reste exportée. |
| `backend/src/iryx/analytics/schemas.py:310` | `UndatedFactOut` n'interdit pas explicitement un timestamp non nul | `low` | Réel. Patch appliqué : validateur `@field_validator("timestamp_utc")` forçant `None`. |
| `backend/src/iryx/analytics/schemas.py:347` | Échec de calcul si `total_events` ou `total_undated` vaut `None` | `low` | Réel. Patch appliqué : test `data.get(...) is None`. |
| `backend/src/iryx/analytics/services.py:485` | Signature opaque du descripteur de méthode polymorphe | `low` | Acceptable en l'état : fonctionnalité couverte et validée par 25 tests unitaires. |
| `backend/src/iryx/analytics/services.py:589` | Risque d'exception sur chaîne d'horodatage malformée | `low` | Réel. Patch appliqué : capture de `(ValueError, TypeError)` et repli vers faits non horodatés. |
| `backend/src/iryx/analytics/models.py:140` | Index composite `(case_id, timestamp_utc)` manquant | `defer` | Reporté dans `deferred-work.md` : optimisation de performance requérant migration Alembic pour Story 7.2. |
| `backend/src/iryx/analytics/services.py:395` | Logger inutilisé et gestion silencieuse des erreurs | `low` | Traité dans les blocs d'interception sécurisés. |
| `backend/src/iryx/analytics/schemas.py:301` | Assomption implicite UTC sur datetime naïf | `false` | Réfutation : Comportement spécifié par conception dans les règles DFIR du projet. |
| `backend/src/iryx/analytics/services.py:576` | Risque d'erreur si `case_id` est passé en tant que `str` | `low` | Réel. Patch appliqué : conversion sécurisée `uuid.UUID(str(case_id))`. |
| `backend/tests/unit/test_timeline_service.py` | Lacune de vérification sur `source_location`, `details` et `tool_execution_id` | `medium` | Réel. Patch appliqué : assertions explicites ajoutées sur les événements datés et non datés. |
| `backend/tests/unit/test_timeline_service.py` | Lacune de vérification directe de `obs.timestamp_utc.tzinfo == UTC` | `medium` | Réel. Patch appliqué : assertions directes ajoutées sur l'instance de modèle. |

## Design Notes

`TimelineService` exécute une requête SQLAlchemy avec jointure externe gauche sur `Evidence` :
```python
stmt = (
    select(Observation, Evidence.original_name)
    .outerjoin(Evidence, Observation.source_id == Evidence.id)
    .where(Observation.case_id == case_id)
    .order_by(Observation.timestamp_utc.asc().nulls_last(), Observation.id.asc())
)
```
Les observations avec `timestamp_utc` sont projetées en `TimelineEventOut`, et celles avec `timestamp_utc is None` en `UndatedFactOut`.
L'extraction de résumé examine en priorité les champs `summary`, `message`, `description`, `event_description`, `command_line` ou génère un condensé textuel structuré.

## Verification

**Commands:**
- `uv run --project backend pytest backend/tests/unit/test_timeline_service.py` -- expected: Tous les tests unitaires de `TimelineService` passent avec succès.
- `uv run --project backend pytest` -- expected: La suite de tests globale (757+ tests) passe intégralement sans régression.
