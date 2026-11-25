---
title: 'Story 8.1 : Module de pseudonymisation déterministe Microsoft Presidio (FR25, D-19, NFR-SEC-07)'
type: 'feature'
created: '2026-11-25'
status: 'done'
baseline_commit: '1b28f0ac054540689af84bac2cdeeb243e8037e9'
baseline_revision: '8bfe83c68dac58b90705d677a68f7d6b9d709a7d'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
warnings: []
deferred:
  - summary: >-
      Prévoir une rotation des clés et un re-chiffrement des jetons
    evidence: |-
      Le contrat gèle une clé dérivée de secret_key et case_id ; aucune exigence de rotation n'est formulée et aucun scénario de rotation n'est démontré.
    location: >-
      backend/src/iryx/reporting/pseudonymizer.py:180
    severity: medium
---

<intent-contract>

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les données d'enquête et observations forensiques contiennent des identifiants techniques et informations sensibles (adresses IP internes, noms de machines, comptes de domaine, emails) qui ne doivent en aucun cas être divulgués à des services tiers ou modèles LLM externes non souverains.

**Approach:** Implémenter le composant de pseudonymisation `DeterministicPseudonymizer` dans `iryx.reporting.pseudonymizer` reposant sur Microsoft Presidio (`presidio-analyzer` et `presidio-anonymizer`, D-19), enrichi de reconnaisseurs personnalisés pour les artefacts techniques et d'une table de correspondances chiffrée par dossier (Fernet) garantissant la cohérence et le déterminisme des pseudonymes sur l'ensemble de l'enquête sans jamais exposer la table hors du serveur.

## Boundaries & Constraints

**Always:**
- Utiliser Microsoft Presidio (`presidio-analyzer` et `presidio-anonymizer` >=2.2.366) combiné à des `PatternRecognizer` personnalisés pour les adresses IP, noms d'hôtes et comptes utilisateurs.
- Remplacement déterministe et stable par dossier : une même valeur au sein d'un même `case_id` reçoit toujours strictement le même pseudonyme (ex: `IP_INTERNAL_1`, `HOST_SERVER_01`, `USER_ACCOUNT_A`).
- Isolation stricte des tables de correspondances par `case_id` : aucun partage ni interférence de pseudonymes entre dossiers différents.
- Chiffrement symétrique de la table de correspondances locale à l'aide d'une clé dérivée de `Settings.secret_key` et du `case_id` (via `cryptography.fernet.Fernet`).
- Conservation intégrale de la structure syntaxique et du contenu lorsque le texte ne contient aucune entité sensible ou lorsqu'il est vide.

**Never:**
- Ne jamais transmettre la table de correspondances ni aucune donnée dé-pseudonymisée aux API LLM externes ou dans les logs.
- Ne jamais altérer la base de données relationnelle (aucun modèle ORM ni migration Alembic dans cette story ; les modèles de rapport et d'audit relèvent des stories 8.3 et 8.5).
- Ne pas utiliser de modèles NLP lourds ou non installés hors ligne sans repli déterministe par expressions régulières.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Détection nominale IP, Host, Compte | Texte brut avec IP `192.168.1.50`, machine `SRV-DC-01`, compte `admin_ad` pour `case_id` | Texte avec `IP_INTERNAL_1`, `HOST_SERVER_01`, `USER_ACCOUNT_A` et métadonnées d'entités détectées | N/A |
| Déterminisme intra-dossier | Deux textes successifs contenant la même IP `192.168.1.50` pour le même `case_id` | Même pseudonyme `IP_INTERNAL_1` attribué dans les deux sorties | N/A |
| Isolation multi-dossiers | Même IP `192.168.1.50` traitée pour `case_A` et `case_B` | Tables de correspondances indépendantes et chiffrées séparément | N/A |
| Dé-pseudonymisation locale contrôlée | Texte pseudonymisé avec table chiffrée valide pour le `case_id` | Restitution exacte du texte d'origine côté serveur | Si clé ou hash corrompu, levée d'une exception contrôlée |
| Texte sans entités sensibles | Texte technique ou narratif neutre sans IP, host, email ou compte | Texte strictement identique retourné intact | N/A |
| Texte vide ou blancs seuls | Chaîne vide `""` ou espaces | Chaîne vide retournée sans déclenchement d'analyseur | N/A |

</frozen-after-approval>

</intent-contract>

## Code Map

- `backend/pyproject.toml:34-36` -- Dépendances `presidio-analyzer>=2.2.366`, `presidio-anonymizer>=2.2.366`, `cryptography>=42.0.0` ; plancher relevé après vérification d'incompatibilité de `2.2.35`.
- `backend/src/iryx/core/config.py:10-30,95-98` -- `Settings.secret_key` obligatoire et `get_settings()` mis en cache ; source unique de la clé de dérivation Fernet.
- `backend/src/iryx/reporting/schemas.py:20-163` -- `PseudonymizeRequest`, `DetectedEntityInfo`, `PseudonymizeResult` déjà définis en Pydantic v2 ; réutiliser tels quels, valeur d'origine absente des métadonnées.
- `backend/src/iryx/reporting/__init__.py` -- À créer ; exporte `DeterministicPseudonymizer`, `CasePseudonymStore`, `PseudonymStoreError` et les schémas publics.
- `backend/src/iryx/reporting/pseudonymizer.py` -- À créer ; `CasePseudonymStore` (clé Fernet dérivée de `secret_key` + `case_id`, jeton chiffré comme état canonique) et `DeterministicPseudonymizer` (analyseur Presidio + `PatternRecognizer` + opérateur d'anonymisation personnalisé).
- `backend/tests/unit/test_pseudonymizer.py` -- À créer ; couvre la matrice I/O et les contraintes de sécurité avec le `SECRET_KEY` de test défini dans `backend/tests/conftest.py:16`.
- API Presidio vérifiée localement : `NlpEngineProvider(nlp_configuration={"nlp_engine_name": "no_op", "models": [{"lang_code": "en", "model_name": "noop"}]})` évite tout téléchargement de modèle ; `AnalyzerEngine(registry=RecognizerRegistry(recognizers=[...]), nlp_engine=..., supported_languages=["en"])` ; `AnonymizerEngine.add_anonymizer()` accepte un `Operator` dont `operator_name()` et `operator_type()` sont des méthodes ; `anonymize(..., merge_entities_with_spaces=False)` préserve la structure du texte.

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/reporting/__init__.py` -- Créer le package et exporter les classes publiques -- Point d'entrée stable pour les stories 8.2 à 8.5.
- [x] `backend/src/iryx/reporting/pseudonymizer.py` -- Implémenter `PseudonymStoreError`, `CasePseudonymStore` (JSON sérialisé puis chiffré par `Fernet`, clé = SHA-256 de `secret_key`/`case_id`, import/export du jeton, exceptions contrôlées) et `DeterministicPseudonymizer` (quatre `PatternRecognizer` : `IP_ADDRESS`, `HOSTNAME`, `USER_ACCOUNT`, `EMAIL_ADDRESS`; moteur `no_op`; opérateur `pseudonymize` résolvant chaque valeur via le magasin; `pseudonymize()` et `depseudonymize()` prenant un `case_id`) -- Cœur métier FR25 / D-19, sans ORM ni migration.
- [x] `backend/tests/unit/test_pseudonymizer.py` -- Tester chaque scénario de la matrice I/O, le déterminisme, l'isolation, le round-trip chiffré, la dé-pseudonymisation et le jeton corrompu -- Non-régression et preuve de non-divulgation.

**Acceptance Criteria:**
- Given une requête `PseudonymizeRequest` valide, when `pseudonymize()` est appelée, then le résultat est un `PseudonymizeResult` typé dont chaque `DetectedEntityInfo` contient le type, la position, le score et le pseudonyme, jamais la valeur sensible d'origine.
- Given un jeton chiffré exporté pour un dossier, when une nouvelle instance recharge ce jeton pour le même `case_id`, then les pseudonymes déjà attribués sont réutilisés et le jeton ne contient aucune valeur en clair.
- Given un jeton chiffré altéré ou une clé invalide, when le magasin tente de le charger, then `PseudonymStoreError` est levée sans exposer la valeur d'origine ni la clé.
- Given des instances créées pour deux `case_id` distincts avec la même `secret_key`, when les clés Fernet sont dérivées, then elles sont différentes et aucun pseudonyme d'un dossier n'est réutilisable dans l'autre.

## Spec Change Log

## Review Triage Log

### 2026-11-25 — Review pass
- verdicts: 22 findings — high 0, medium 9, low 7, false 2, maybe-false 4
- findings:
  - `[low]` `[defer]` Divergence de surface workflow : `sprint-status.yaml` reste `in-progress` et la spec porte `in-review` — déjà consigné dans `deferred` ; ce fichier est piloté par sprint-planning, pas par build-auto.
  - `[false]` `[reject]` Divergence de surface produit : aucune modification H3/LLM/logs — le contrat (Approach) limite explicitement cette story au composant `iryx.reporting.pseudonymizer` ; l'intégration H3 relève des stories suivantes, donc ce n'est pas un défaut de ce changement.
  - `[medium]` `[patch]` Liste `entities` non prise en charge → Presidio reçoit `[]` et analyse tous les détecteurs — vérifié sur la signature brute et sur `PseudonymizeRequest` : validation ajoutée levant `ValueError` avec les types inconnus, test dédié.
  - `[medium]` `[patch]` `register_store()` et `store=` acceptent une table chiffrée avec une clé secrète différente — vérifié : comparaison de la clé dérivée `_key` ajoutée et test `test_store_with_foreign_secret_is_rejected`.
  - `[medium]` `[patch]` `_read_state()` accepte une table sémantiquement invalide (pseudonymes dupliqués, formats incorrects, chaînes vides) — vérifié : validation ajoutée et test avec un jeton chiffré valide contenant un doublon.
  - `[low]` `[patch]` Aucun test de rejet d'un jeton exporté chargé dans un autre dossier — test `test_cross_case_token_is_rejected` ajouté.
  - `[low]` `[patch]` Aucun test d'idempotence malgré les lookaheads négatifs des motifs — test `test_pseudonymization_is_idempotent` ajouté.
  - `[maybe-false]` `[defer]` État `_stores`/`_token` non synchronisé — aucun appelant concurrent n'est démontré ; il faudrait un test de concurrence ou un usage réel avec deux pseudonymisations simultanées sur la même instance pour confirmer la perte de correspondances.
  - `[medium]` `[defer]` Aucune rotation de clé ni re-chiffrement des jetons — le contrat gèle la dérivation depuis `secret_key` et `case_id` et aucune exigence de rotation n'est formulée ; consigné dans `deferred`.
  - `[low]` `[reject]` Recalcul des compteurs sur toute la table et rechiffrement complet à chaque insertion (O(N²)) — le correctif exigerait un cache incrémental ou un batch ; improbable aux tailles de dossier courantes, non rentable ici.
  - `[low]` `[patch]` `export_token()` modifiait l'état canonique sur un magasin neuf — vérifié : `_encrypt_state()` sans effet de bord ajouté et test existant conservé.
  - `[low]` `[reject]` Contradiction de l'acceptation « aucun pseudonyme d'un dossier n'est réutilisable dans l'autre » — le contrat figé définit l'isolation comme l'absence de partage de table, pas l'unicité des étiquettes ; la règle de triage interdit de modifier la spec pour corriger ce libellé.
  - `[low]` `[reject]` `get_store()` conserve toutes les tables sans éviction — le correctif ajouterait une API publique de nettoyage ; aucun besoin n'est démontré pour cette story.
  - `[medium]` `[patch]` Test de restauration trop faible : passe même si `register_store()` est neutralisé — finding pré-vérifié par le layer ; test renforcé avec une seconde IP et l'ordre des pseudonymes (`IP_INTERNAL_1` puis `IP_INTERNAL_2`).
  - `[medium]` `[patch]` Filtre `entities` de la signature texte brut non testé — finding pré-vérifié par le layer ; test `test_raw_text_entity_filter_is_normalized` ajouté.
  - `[medium]` `[patch]` Garde inter-dossiers de `depseudonymize(store=...)` non testée — finding pré-vérifié par le layer ; test `test_depseudonymize_rejects_foreign_store` ajouté.
  - `[medium]` `[patch]` Résolution de `Settings.secret_key` par les constructeurs sans argument non testée — finding pré-vérifié par le layer ; test `test_default_key_comes_from_settings` ajouté.
  - `[medium]` `[patch]` Filtre `entities` sans type pris en charge (même root cause que la troisième entrée) — patch groupé avec elle, même validation ajoutée.
  - `[maybe-false]` `[defer]` Deux appels concurrents peuvent écraser une correspondance (même root cause que la huitième entrée) — reporté avec elle, aucun appelant concurrent démontré.
  - `[maybe-false]` `[defer]` `AnonymizerEngine.add_anonymizer()` absent à la version plancher `2.2.35` — version installée : `2.2.366`, où la méthode existe ; il faudrait installer `2.2.35` et appeler la méthode pour trancher.
  - `[maybe-false]` `[defer]` `anonymize(merge_entities_with_spaces=...)` absent à `2.2.35` → `TypeError` (même cause que la entrée précédente) — même vérification requise sur la version plancher.
  - `[false]` `[reject]` Variable `SECRET_KEY` absente → `KeyError` à l'import du module de test — `backend/tests/conftest.py:16` fixe la variable avant la collecte ; les 25 tests du module passent.

## Design Notes

Le moteur `no_op` de Presidio fournit des artefacts NLP vides : seuls les `PatternRecognizer` déterministes analysent le texte. Aucun modèle SpaCy n'est téléchargé et le comportement reste identique hors ligne. Exemple de flux :

```python
analyzer = AnalyzerEngine(registry=registry, nlp_engine=no_op_engine, supported_languages=["en"])
results = analyzer.analyze(text, language="en")
result = anonymizer.anonymize(
    text, results,
    operators={"IP_ADDRESS": OperatorConfig("pseudonymize", {"resolver": resolver})},
    merge_entities_with_spaces=False,
)
```

Le résolveur reçoit `(entity_type, valeur_originale)` et interroge `CasePseudonymStore`, dont l'état canonique est le jeton Fernet chiffré : chaque mutation rechiffre le JSON complet. Les compteurs par type d'entité sont recalculés depuis le magasin, ce qui rend l'attribution stable même après restauration. Les entités d'un même texte sont attribuées par position croissante. Formats convenus : `IP_INTERNAL_{n}`, `HOST_SERVER_{n:02d}`, `USER_ACCOUNT_{lettre majeure}` (A, B, …), `EMAIL_ADDRESS_{n}`.

## Verification

**Commands:**
- `cd backend && uv run pytest tests/unit/test_pseudonymizer.py -v` -- expected: tous les tests de pseudonymisation passent.
- `cd backend && uv run ruff check src/iryx/reporting tests/unit/test_pseudonymizer.py` -- expected: 0 erreur et 0 avertissement.

## Auto Run Result

Status: blocked
Blocking condition: no subagents

Le moteur `bmad-build-auto` exige un sous-agent synchrone pour l'implémentation. Deux lancements successifs ont échoué avec l'erreur « Free usage limit reached. Connect a provider or subscribe to OpenCode Go to keep going, or switch models. ». Aucun code d'implémentation n'a été produit lors de cette exécution.

Status: blocked
Blocking condition: dirty working tree

Nouvelle tentative « continue la story 8.1 » : le contrôle de cohérence version-control échoue. Après `git add --refresh -- .`, l'arbre de travail reste non propre sur `main` (sprint-status.yaml, pyproject.toml et uv.lock modifiés ; epic-8-context.md, la spec 8.1 et backend/src/iryx/reporting/ non suivis). Aucune planification ni implémentation n'a été reprise.

Blocage levé : l'utilisateur a demandé le commit (`a0730b5`), l'arbre est de nouveau propre et la spec repasse en `draft` pour reprise de la planification.

### Exécution terminée (2026-11-25)

**Résumé** : module de pseudonymisation déterministe implémenté avec Microsoft Presidio (moteur `no_op`, quatre `PatternRecognizer`) et table de correspondances chiffrée par dossier (Fernet, clé dérivée de `secret_key` + `case_id`). Les valeurs sont remplacées par des pseudonymes stables (`IP_INTERNAL_n`, `HOST_SERVER_nn`, `USER_ACCOUNT_X`, `EMAIL_ADDRESS_n`) sans exposer la valeur d'origine dans les métadonnées ni le jeton exporté.

**Fichiers modifiés** :
- `backend/src/iryx/reporting/__init__.py` — package et exports publics du service.
- `backend/src/iryx/reporting/pseudonymizer.py` — `PseudonymStoreError`, `CasePseudonymStore`, `DeterministicPseudonymizer`, opérateur Presidio personnalisé, jeton Fernet et dé-pseudonymisation locale.
- `backend/tests/unit/test_pseudonymizer.py` — 25 tests couvrant la matrice I/O, le déterminisme, l'isolation, la validation du jeton, l'idempotence et les garde-fous de sécurité.
- Spec 8.1 — statut, baseline, tâches, triage de revue et éléments reportés mis à jour.

**Revue** : 22 findings — 0 high, 9 medium, 7 low, 2 false, 4 maybe-false. Correctifs appliqués : 8 entrées `medium` et 3 entrées `low` (11 entrées au total, dont les validations d'entités, de clé et de jeton, l'absence d'effet de bord de `export_token()` et quatre tests de verification-gap). Findings rejetés : complexité O(N²) sans besoin démontré, libellé d'AC à ne pas modifier dans la spec, absence d'éviction des tables sans API publiques justifiée, divergence H3 hors périmètre de cette story, et `KeyError` sur `SECRET_KEY` infirmé par `conftest.py:16`.

**Résolutions post-audit (2026-11-25)** : la synchronisation de `sprint-status.yaml` est traitée par la passe de réconciliation ; un verrou réentrant protège désormais les mutations de `CasePseudonymStore` avec un test de pseudonymisations concurrentes ; le plancher Presidio est relevé à `2.2.366` après vérification que `2.2.35` ne fournit ni moteur `no_op`, ni `add_anonymizer`, ni `merge_entities_with_spaces`. La rotation des clés reste la seule entrée `deferred` de cette story.

**Recommandation de revue de suivi** : `true` — première passe avec plus de deux entrées `medium` corrigées (8 medium, 3 low). Risque précis non vérifié : les motifs de détection restent heuristiques ; un format d'hôte ou de compte hors conventions `SRV-xxxx` / `admin_xx` pourrait échapper à la pseudonymisation, scénario non couvert par la matrice I/O.

**Vérification** : `uv run pytest tests/unit/test_pseudonymizer.py -q` → 25 passed ; `uv run ruff check src/iryx/reporting tests/unit/test_pseudonymizer.py` → All checks passed ; `uv run pytest -q` (backend complet) → 860 passed. Le diff unifié depuis `8bfe83c` a été relu avant et après correctifs.

**Risques résiduels** : détection heuristique limitée aux formats convenus, étiquettes de pseudonymes normalisées partagées entre dossiers (l'isolation porte sur les tables, pas sur les libellés), confidentialité du jeton liée à `SECRET_KEY` et à son non-transit hors serveur, et rotation de clé non traitée (voir `deferred`).
