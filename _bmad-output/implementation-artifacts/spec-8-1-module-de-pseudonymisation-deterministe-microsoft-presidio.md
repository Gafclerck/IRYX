---
title: 'Story 8.1 : Module de pseudonymisation déterministe Microsoft Presidio (FR25, D-19, NFR-SEC-07)'
type: 'feature'
created: '2026-11-25'
status: 'ready-for-dev'
baseline_commit: '1b28f0ac054540689af84bac2cdeeb243e8037e9'
baseline_revision: '1b28f0ac054540689af84bac2cdeeb243e8037e9'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
warnings: []
deferred: []
---

<intent-contract>

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les données d'enquête et observations forensiques contiennent des identifiants techniques et informations sensibles (adresses IP internes, noms de machines, comptes de domaine, emails) qui ne doivent en aucun cas être divulgués à des services tiers ou modèles LLM externes non souverains.

**Approach:** Implémenter le composant de pseudonymisation `DeterministicPseudonymizer` dans `iryx.reporting.pseudonymizer` reposant sur Microsoft Presidio (`presidio-analyzer` et `presidio-anonymizer`, D-19), enrichi de reconnaisseurs personnalisés pour les artefacts techniques et d'une table de correspondances chiffrée par dossier (Fernet) garantissant la cohérence et le déterminisme des pseudonymes sur l'ensemble de l'enquête sans jamais exposer la table hors du serveur.

## Boundaries & Constraints

**Always:**
- Utiliser Microsoft Presidio (`presidio-analyzer` et `presidio-anonymizer` >=2.2.35) combiné à des `PatternRecognizer` personnalisés pour les adresses IP, noms d'hôtes et comptes utilisateurs.
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

- `backend/pyproject.toml:34-36` -- Dépendances `presidio-analyzer>=2.2.35`, `presidio-anonymizer>=2.2.35`, `cryptography>=42.0.0` déjà déclarées et présentes dans `uv.lock` ; lecture seule, aucune modification requise.
- `backend/src/iryx/core/config.py:10-30,95-98` -- `Settings.secret_key` obligatoire et `get_settings()` mis en cache ; source unique de la clé de dérivation Fernet.
- `backend/src/iryx/reporting/schemas.py:20-163` -- `PseudonymizeRequest`, `DetectedEntityInfo`, `PseudonymizeResult` déjà définis en Pydantic v2 ; réutiliser tels quels, valeur d'origine absente des métadonnées.
- `backend/src/iryx/reporting/__init__.py` -- À créer ; exporte `DeterministicPseudonymizer`, `CasePseudonymStore`, `PseudonymStoreError` et les schémas publics.
- `backend/src/iryx/reporting/pseudonymizer.py` -- À créer ; `CasePseudonymStore` (clé Fernet dérivée de `secret_key` + `case_id`, jeton chiffré comme état canonique) et `DeterministicPseudonymizer` (analyseur Presidio + `PatternRecognizer` + opérateur d'anonymisation personnalisé).
- `backend/tests/unit/test_pseudonymizer.py` -- À créer ; couvre la matrice I/O et les contraintes de sécurité avec le `SECRET_KEY` de test défini dans `backend/tests/conftest.py:16`.
- API Presidio vérifiée localement : `NlpEngineProvider(nlp_configuration={"nlp_engine_name": "no_op", "models": [{"lang_code": "en", "model_name": "noop"}]})` évite tout téléchargement de modèle ; `AnalyzerEngine(registry=RecognizerRegistry(recognizers=[...]), nlp_engine=..., supported_languages=["en"])` ; `AnonymizerEngine.add_anonymizer()` accepte un `Operator` dont `operator_name()` et `operator_type()` sont des méthodes ; `anonymize(..., merge_entities_with_spaces=False)` préserve la structure du texte.

## Tasks & Acceptance

**Execution:**
- `backend/src/iryx/reporting/__init__.py` -- Créer le package et exporter les classes publiques -- Point d'entrée stable pour les stories 8.2 à 8.5.
- `backend/src/iryx/reporting/pseudonymizer.py` -- Implémenter `PseudonymStoreError`, `CasePseudonymStore` (JSON sérialisé puis chiffré par `Fernet`, clé = SHA-256 de `secret_key`/`case_id`, import/export du jeton, exceptions contrôlées) et `DeterministicPseudonymizer` (quatre `PatternRecognizer` : `IP_ADDRESS`, `HOSTNAME`, `USER_ACCOUNT`, `EMAIL_ADDRESS`; moteur `no_op`; opérateur `pseudonymize` résolvant chaque valeur via le magasin; `pseudonymize()` et `depseudonymize()` prenant un `case_id`) -- Cœur métier FR25 / D-19, sans ORM ni migration.
- `backend/tests/unit/test_pseudonymizer.py` -- Tester chaque scénario de la matrice I/O, le déterminisme, l'isolation, le round-trip chiffré, la dé-pseudonymisation et le jeton corrompu -- Non-régression et preuve de non-divulgation.

**Acceptance Criteria:**
- Given une requête `PseudonymizeRequest` valide, when `pseudonymize()` est appelée, then le résultat est un `PseudonymizeResult` typé dont chaque `DetectedEntityInfo` contient le type, la position, le score et le pseudonyme, jamais la valeur sensible d'origine.
- Given un jeton chiffré exporté pour un dossier, when une nouvelle instance recharge ce jeton pour le même `case_id`, then les pseudonymes déjà attribués sont réutilisés et le jeton ne contient aucune valeur en clair.
- Given un jeton chiffré altéré ou une clé invalide, when le magasin tente de le charger, then `PseudonymStoreError` est levée sans exposer la valeur d'origine ni la clé.
- Given des instances créées pour deux `case_id` distincts avec la même `secret_key`, when les clés Fernet sont dérivées, then elles sont différentes et aucun pseudonyme d'un dossier n'est réutilisable dans l'autre.

## Spec Change Log

## Review Triage Log

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
