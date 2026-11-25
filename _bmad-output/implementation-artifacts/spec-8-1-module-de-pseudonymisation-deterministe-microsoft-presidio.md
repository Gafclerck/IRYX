---
title: "Story 8.1 : Module de pseudonymisation déterministe Microsoft Presidio (FR25, D-19, NFR-SEC-07)"
type: 'feature'
created: '2026-11-25'
status: 'blocked'
baseline_commit: '1b28f0ac054540689af84bac2cdeeb243e8037e9'
baseline_revision: '1b28f0ac054540689af84bac2cdeeb243e8037e9'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
---

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

## Code Map

- `backend/pyproject.toml` -- Déclaration des dépendances `presidio-analyzer>=2.2.35`, `presidio-anonymizer>=2.2.35`, `cryptography>=42.0.0`
- `backend/src/iryx/core/config.py` -- Lecture de `Settings.secret_key` pour dérivation de la clé de scellement / chiffrement des correspondances
- `backend/src/iryx/reporting/__init__.py` -- Package métier reporting
- `backend/src/iryx/reporting/schemas.py` -- Schémas Pydantic v2 `PseudonymizeRequest`, `PseudonymizeResult`, `DetectedEntityInfo`
- `backend/src/iryx/reporting/pseudonymizer.py` -- Moteur `DeterministicPseudonymizer` avec reconnaisseurs de motifs techniques et magasin chiffré `CasePseudonymStore`
- `backend/tests/unit/test_pseudonymizer.py` -- Tests unitaires pour la détection, le déterminisme, l'isolation par dossier et les cas d'erreur

## Tasks & Acceptance

**Execution:**
- [ ] `backend/pyproject.toml` -- Ajouter les dépendances `presidio-analyzer`, `presidio-anonymizer` et `cryptography` et synchroniser l'environnement -- Nécessaire pour D-19 et le chiffrement local
- [ ] `backend/src/iryx/reporting/__init__.py` -- Créer le module reporting et exporter les classes publiques -- Point d'entrée du package
- [ ] `backend/src/iryx/reporting/schemas.py` -- Définir les schémas Pydantic v2 pour les requêtes, résultats et entités détectées -- Typage strict et validation
- [ ] `backend/src/iryx/reporting/pseudonymizer.py` -- Implémenter `CasePseudonymStore` (chiffrement Fernet local) et `DeterministicPseudonymizer` (moteur Presidio + recognizers personnalisés) -- Cœur métier FR25 / D-19
- [ ] `backend/tests/unit/test_pseudonymizer.py` -- Implémenter les tests unitaires couvrant l'ensemble de la matrice I/O et les contraintes de sécurité -- Vérification de non-régression et d'isolation

**Acceptance Criteria:**
- Given un texte contenant des adresses IP internes (`192.168.1.50`), des noms d'hôtes (`SRV-DC-01`) et des comptes (`admin_ad`), when le service de pseudonymisation est exécuté pour un `case_id`, then les entités sensibles sont détectées et substituées par des pseudonymes stables au sein du dossier et la table de correspondances locale est chiffrée.
- Given un texte contenant des entités sensibles déjà indexées pour le même dossier, when la pseudonymisation est sollicitée, then les mêmes pseudonymes sont réattribués de manière strictement déterministe.
- Given un texte ne contenant aucune entité sensible détectée, when la pseudonymisation est appliquée, then le texte est retourné intact sans altération de sa structure syntaxique.
- Given deux dossiers distincts `case_1` et `case_2`, when la pseudonymisation est exécutée, then leurs tables de correspondances restent étanches et indépendantes.

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Design Notes

Pour garantir l'exécution sans dépendre du téléchargement d'un modèle lourd SpaCy, `DeterministicPseudonymizer` configure Presidio avec un `NlpEngineProvider` léger ou configure des `PatternRecognizer` dédiés pour les types critiques DFIR :
- `IP_ADDRESS` : expressions régulières IPv4 et IPv6 (gestion des IP privées et publiques).
- `HOSTNAME` : expressions régulières pour machines Windows / serveurs (ex. `SRV-.*`, `DC-.*`, `DESKTOP-.*`, `WORKSTATION-.*`, FQDNs).
- `ACCOUNT` : expressions régulières pour comptes de domaine (`DOMAIN\\user`, `admin_.*`, `svc_.*`).
- `EMAIL_ADDRESS` : détection d'adresses de courriel.

La classe `CasePseudonymStore` gère la correspondance bidirectionnelle `(entity_type, original_value) <-> pseudonym` en mémoire pour le dossier, avec sérialisation chiffrée (Fernet) dérivée de `secret_key` et `case_id`.

## Verification

**Commands:**
- `cd backend && uv run pytest tests/unit/test_pseudonymizer.py -v` -- expected: Tous les tests unitaires de pseudonymisation passent avec succès.
- `cd backend && uv run ruff check src/iryx/reporting tests/unit/test_pseudonymizer.py` -- expected: 0 erreur et 0 avertissement.

## Auto Run Result

Status: blocked
Blocking condition: no subagents

Le moteur `bmad-build-auto` exige un sous-agent synchrone pour l'implémentation. Deux lancements successifs ont échoué avec l'erreur « Free usage limit reached. Connect a provider or subscribe to OpenCode Go to keep going, or switch models. ». Aucun code d'implémentation n'a été produit lors de cette exécution.

Status: blocked
Blocking condition: dirty working tree

Nouvelle tentative « continue la story 8.1 » : le contrôle de cohérence version-control échoue. Après `git add --refresh -- .`, l'arbre de travail reste non propre sur `main` (sprint-status.yaml, pyproject.toml et uv.lock modifiés ; epic-8-context.md, la spec 8.1 et backend/src/iryx/reporting/ non suivis). Aucune planification ni implémentation n'a été reprise.
