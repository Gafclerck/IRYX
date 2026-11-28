---
title: 'Story 9.3 : Script de peuplement de démonstration (Seed Data) d''un incident Windows type'
type: 'feature'
created: '2026-11-27'
status: 'done'
baseline_commit: 'e15f2c07ec1ac899d85312402844674c4118e760'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-9-context.md'
---

<!-- Target: 900–1300 tokens. -->

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'environnement Docker peut démarrer vide : sans organisation, comptes, dossier et preuves scellées, la démonstration et le smoke test E2E exigent une préparation manuelle fragile et non reproductible.

**Approach:** Ajouter un module CLI `python -m iryx.scripts.seed_data` idempotent qui crée/actualise les données de démo via ORM SQLAlchemy, écrit les preuves de démonstration dans le staging configuré, puis scelle chaque preuve avec le chemin réel d'ingestion (SHA-256, type détecté, `0o440`, `IngestionRun` terminé).

## Boundaries & Constraints

**Always:** Commande `uv run python -m iryx.scripts.seed_data` ; org « Banque Atlantique DFIR » ; 4 users actifs avec mots de passe de démo fixes hachés argon2 : `admin@iryx.local`/`Admin12345!` (admin), `analyst@iryx.local`/`Analyst12345!` (analyst), `investigator@iryx.local`/`Investigator12345!` (investigator), `auditor@iryx.local`/`Auditor12345!` (viewer). Dossier « Attaque Ransomware Serveur AD » en `open`. 3 preuves générées programmatiquement de façon déterministe (aucun binaire opaque versionné), écrites en staging puis scellées : `Security.evtx` (contient Event IDs 4624/4688), `POWERSHELL.EXE-DEMO1234.pf`, extrait dump mémoire de test. Idempotence totale à la seconde exécution (aucune erreur de contrainte SQL, pas de doublon). Résumé final affichant les identifiants de démo et rappelant d'utiliser des mots de passe robustes/personnalisés hors démonstration. Utiliser `SessionLocal`/`get_settings`, respecter `evidence_staging_path`.

**Decisions (human):** 1A — mots de passe de démo fixes documentés comme ci-dessus. 2A — fixtures de preuves générées programmatiquement, déterministes, sans binaires versionnés.

**Never:** Ne pas modifier `backend/src` hors `iryx/scripts/**` (et `__init__` requis), pas de `create_all`, pas de suppression de données existantes non liées à la démo, pas de dépendance au broker Celery en fonctionnement, pas de téléchargement réseau, pas de secret en dur dans le compose ou le code hors constantes de démo clairement identifiées.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Nominal | DB migrée vide, staging accessible | Org, 4 memberships, case, 3 evidences + 3 ingestion runs `completed`, SHA-256 et `detected_type` renseignés, fichiers staging `0o440` | Sortie non nulle avec message explicite sur échec DB/fichier |
| Seconde exécution | Données de démo déjà présentes | Aucun doublon, aucune violation SQL ; données manquantes réparées ; résumé affiché | Log/affichage clair si un élément est ignoré/réparé |
| Preuve partiellement scellée | Evidence existe, SHA-256 absent ou run non complété | Réutilise l'evidence, régénère/resscelle selon besoin via logique d'ingestion | Échec explicite si fichier staging absent et non recréable |
| Utilisateur existant email identique | User déjà présent | Réutilise l'utilisateur, met à jour hash si mot de passe de démo attendu absent/invalide uniquement selon stratégie idempotente sûre ; ne duplique pas | Ne jamais supprimer l'utilisateur existant |
| Staging non accessible | `evidence_staging_path` absent/non écrivable | Création du répertoire tentée ; échec clair si impossible | Exception capturée, message actionnable, exit code != 0 |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/db/session.py:30-100` -- `SessionLocal`, `get_db_session`, gestion erreurs DB ; réutiliser `SessionLocal` pour le CLI.
- `backend/src/iryx/core/config.py:49-110` -- `get_settings()`, `evidence_staging_path` (défaut `storage/staging`) ; source des chemins.
- `backend/src/iryx/core/security.py:37-48` -- `hash_password` argon2id ; utiliser pour les 4 comptes.
- `backend/src/iryx/auth/models.py:26-163` -- `MembershipRole`, `Organization`, `User`, `Membership`, contraintes unicité/rôle.
- `backend/src/iryx/cases/models.py:29-132` -- `Case`, `CaseStatus.OPEN`, FK org/creator.
- `backend/src/iryx/evidence/models.py:29-170` -- `Evidence`, `IngestionRun`, `IngestionStatus`, progress 0-100.
- `backend/src/iryx/evidence/tasks.py:25-239` -- `process_evidence_ingestion` : valide staging, chmod `0o440`, SHA-256 64Ko, filetype, complète run. Réutilisable en appel direct synchrone.
- `backend/src/iryx/evidence/services.py:63-74,145-166` -- contrat staging `{evidence_id}.bin`, chmod/dispatch Celery (à ne pas reproduire côté seed ; préférer appel direct de la tâche).
- `backend/tests/unit/test_evidence_ingestion_task.py:36-120` -- pattern `SessionLocal` patching et assertions de scellement.
- `README.md`, `backend/.env.example` -- documenter l'usage seed si pertinent (README section déploiement/démo).

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/scripts/__init__.py` -- créer le package scripts -- point d'entrée module.
- [x] `backend/src/iryx/scripts/seed_data.py` -- implémenter le seed idempotent (org/users/memberships/case/evidences), génération/écriture des fixtures démo, scellement via `process_evidence_ingestion`, résumé + avertissement mot de passe -- cœur Story 9.3.
- [x] `backend/src/iryx/scripts/demo_evidence.py` (ou module équivalent) -- fournir des générateurs/bytes déterministes pour `Security.evtx` (4624/4688), `POWERSHELL.EXE-DEMO1234.pf`, dump mémoire test -- preuves réalistes de test, sans binaires opaques inutiles.
- [x] `backend/tests/unit/test_seed_data.py` -- couvrir nominal, idempotence seconde exécution, scellement (SHA-256, type, 0440, run completed), avertissement mot de passe, absence d'erreur SQL -- validation AC.
- [x] `README.md` -- ajouter commande seed et prérequis (DB migrée, `.env`) dans la section déploiement/démo -- opérabilité.

**Acceptance Criteria:**
- Given une base migrée, when `uv run python -m iryx.scripts.seed_data` s'exécute, then l'org « Banque Atlantique DFIR », les 4 comptes/rôles demandés, le dossier `open` « Attaque Ransomware Serveur AD » et 3 preuves scellées existent.
- Given une seconde exécution, when le seed relance les contrôles d'unicité, then aucune contrainte SQL n'échoue et aucun doublon métier n'est créé.
- Given les mots de passe de démo, when le résumé s'affiche, then il rappelle d'utiliser des mots de passe robustes/personnalisés hors production.

## Implementation Notes

<!-- Append-only. -->

- 2026-11-28 — `demo_evidence.py` génère trois fixtures déterministes en mémoire :
  - `Security.evtx` est un vrai conteneur EVTX (en-tête fichier `ElfFile`, chunk `ElfChnk`, enregistrements et template BXml résident) lisible par `python-evtx` et `EvtxParserTool` ; il contient les Event IDs 4624 et 4688.
  - `POWERSHELL.EXE-DEMO1234.pf` est un Prefetch SCCA v30 non compressé construit avec les structures `dissect` et validé par `PrefetchParserTool`.
  - `MEMORY.DMP` est un minidump synthétique déterministe, volontairement partiel (extrait de démonstration, pas une image RAM complète).
- 2026-11-28 — `seed_data.py` sépare la préparation (org, 4 users argon2id, memberships, case `open`, evidence rows, runs, fichiers staging) du scellement (appel direct de `process_evidence_ingestion`, sans broker Celery). La seconde exécution réutilise les lignes existantes, répare les hash/type/runs manquants et ne recrée pas de fichiers identiques.
- 2026-11-28 — Le mot de passe argon2id n'est réhaché que si `verify_password` échoue ; un compte existant n'est jamais supprimé. Le case de démo est ramené à `open` et son `created_by` complété si absent.
- 2026-11-28 — Le seed importe `iryx.analytics.models` en premier afin de contourner un cycle d'import préexistant `analytics` ↔ `cases` lorsque le module est le point d'entrée CLI (`python -m ...`).
- 2026-11-28 — `detected_type` vaut `application/octet-stream` pour les trois fixtures, `filetype` ne disposant pas de signature EVTX/Prefetch/minidump ; le champ reste renseigné et non nul.
- 2026-11-28 — Les permissions scellées sont appliquées via `os.chmod(..., 0o440)` ; sous Windows, cela se traduit par l'attribut lecture seule (`0o444` dans `stat`). Les tests vérifient l'absence de bits d'écriture (`mode & 0o222 == 0`).


## Spec Change Log

<!-- Append-only. -->

- 2026-11-28 — Correction du `baseline_commit` frontmatter : la valeur `e15f2c06c5cd7b09757f77d039f74347b29fcd86` ne résolvait pas dans le dépôt (objet introuvable). Remplacée par l'identifiant canonique HEAD `e15f2c07ec1ac899d85312402844674c4118e760` (même commit de départ, short hash `e15f2c0`). Aucun changement de périmètre.

## Review Triage Log

<!-- Append-only. -->

- 2026-11-28 — Revue step-04. Les sous-agents `edge-case-hunter` et `verification-gap`, puis le premier `blind-hunter`, ont échoué (« Free usage limit reached »). Une seule relance `blind-hunter` (session `ses_ddf79a21bffeedlF7yPsU3Xb37`) a produit 10 constats ; vérification manuelle effectuée. Aucun `intent_gap`/`bad_spec`. Deux `patch` appliqués + retest vert.
- 2026-11-28 — [1] `false` : `in-review` est exigé par step-04 pour le statut du fichier spec ; `sprint-status.yaml` autorise `review` mais sa synchronisation n'est pas demandée ici ; pas de défaut fonctionnel. Corriger = éditer ce spec.
- 2026-11-28 — [2] `false` : le Code Map décrit le défaut réel (`evidence_staging_path=""` → `{evidence_storage_path}/staging`, `/data/evidence/`, Compose `/data/evidence/staging`) ; texte informatif, corriger = éditer ce spec ; aucun effet code. (À rafraîchir hors revue.)
- 2026-11-28 — [3] `patch` : `_ensure_ingestion_run` réinitialise désormais si `run.progress != 100`, évitant `SeedDataError` après court-circuit idempotent de `process_evidence_ingestion`. Test `test_seed_repairs_completed_run_with_progress_below_100`.
- 2026-11-28 — [4] `maybe-false` : `_ensure_user` remet `is_active=True` et réhache si `verify_password` échoue pour les 4 emails de démo, conformément à la matrice « Utilisateur existant email identique » ; il ne supprime rien. Ce qui manque : preuve qu'un compte homonyme non lié à la démo existe ; `fact: _ensure_user` ne filtre que par email.
- 2026-11-28 — [5] `maybe-false` : `_ensure_membership` ne met à jour que `membership.organization_id == org.id` du `membership.user_id` correspondant vers le rôle de démo. Ce qui manque : preuve qu'une appartenance préexistante dans l'org de démo n'est pas liée à la démo.
- 2026-11-28 — [6] `patch` : `.expanduser()` retiré de `_ensure_staging_directory` pour respecter la vérification `Path(...).resolve()` sans `expanduser` de `process_evidence_ingestion` (`Chemin de staging non autorisé`).
- 2026-11-28 — [7] `low` : `_prepare_staging_file` écrit avant `db.commit()` ; un échec commit/écriture peut laisser `{uuid}.bin` orphelin. Non corrigé (scénario non démontré, prochaine exécution répare) ; pas de suppression d'objets non liés.
- 2026-11-28 — [8] `maybe-false` : sélection du dernier run `started_at.desc(), id.desc()` dans le seed vs `started_at.desc()` dans `process_evidence_ingestion` (inmodifiable hors `scripts/**`). Nécessite une preuve de `started_at` identiques entre plusieurs runs ; le seed ne crée qu'un run par preuve.
- 2026-11-28 — [9] `defer` : unicité `Organization.name` / `Case(organization_id,title)` / `Evidence(case_id,original_name)` et verrouillage concurrent absents en base ; nécessite migration hors `backend/src/iryx/scripts/**`, non autorisé. Idempotence séquentielle seulement.
- 2026-11-28 — [10] `low` : `_verify_sealed_evidence` revérifie la base mais pas le fichier `staging_path` (taille/sha/lecture seule). `_apply_sealed_permissions` s'exécute juste avant et lève sur `os.chmod`. Confort, pas invariant de l'AC.
- 2026-11-28 — Reprise revue step-04 : couches `edge-case-hunter` et `verification-gap` (sous-agents `dcfac9ff-ff62-450e-b2a5-06e77249afe2` et `d11b5ad7-aa91-4d38-8386-7f135bea9e58`). Aucun `intent_gap`/`bad_spec`, aucun nouveau `defer` ; 5 `patch` appliqués (`seed_data.py` + `test_seed_data.py`).
- 2026-11-28 — [EC-1] `medium` (`patch`) : `_ensure_staging_directory` acceptait `""` ou des espaces (`Settings.set_default_staging_path` laisse passer `"   "` et `Path("")` résout vers le répertoire courant). Garde ajouté sur `not staging_path or not staging_path.strip()` + test `test_main_returns_nonzero_when_staging_path_is_blank`.
- 2026-11-28 — [EC-2] `false` : en cas de course concurrente sur `User`/`Membership`, `db.flush()` lève `IntegrityError` et `main()` échoue bruyamment (code 1, message sur stderr) sans corrompre la base ; l'idempotence spécifiée est séquentielle (concurrence globale déjà traitée en [9]).
- 2026-11-28 — [EC-3] `carried` (`maybe-false` / [8]) : sélection du dernier `IngestionRun` à `started_at` identiques entre `seed_data.py:247-268` et `process_evidence_ingestion` ; déjà consigné en [8], code inchangé.
- 2026-11-28 — [EC-4] `maybe-false` (rejeté, serait `low`) : `_prepare_staging_file` suit un éventuel lien symbolique `{uuid}.bin` avant `process_evidence_ingestion`. Ce qui manque : preuve qu'un lien symbolique puisse apparaître dans le dossier privé `evidence_staging_path` sans accès écriture préalable compromis sur le volume.
- 2026-11-28 — [EC-5] `carried` (`low` / [7]) : `_prepare_staging_file` écrit avant `db.commit()` (`seed_data.py:373-384`), pouvant laisser `{uuid}.bin` orphelin en cas d'échec ; déjà consigné en [7], code inchangé.
- 2026-11-28 — [EC-6] `false` : `_EvtxChunkBuilder` est privé et appelé uniquement par `generate_security_evtx()` qui ajoute 3 enregistrements ; `self._record_offsets[-1]` à 0 enregistrement est inatteignable.
- 2026-11-28 — [EC-7] `false` : `_EvtxChunkBuilder.add_record` n'est appelé qu'avec les littéraux statiques courts de `generate_security_evtx()` (< 100 caractères) et un chunk est borné à 64 Kio ; le dépassement > 65 535 octets dans `struct.pack("<HB", ...)` est inatteignable.
- 2026-11-28 — [VG-1] `medium` (`patch`, pré-vérifié) : la fixture `POWERSHELL.EXE-DEMO1234.pf` n'était pas validée par `PrefetchParserTool` dans `test_seed_data.py`. Test `test_seeded_prefetch_is_parsed_by_prefetch_parser_tool` ajouté.
- 2026-11-28 — [VG-2] `medium` (`patch`, pré-vérifié) : la réécriture et le rescellement `0o440` d'un fichier staging corrompu mais déjà `COMPLETED`/`sha256` en base n'étaient pas testés. Test `test_seed_repairs_corrupted_readonly_staging_file` ajouté.
- 2026-11-28 — [VG-3] `medium` (`patch`, pré-vérifié) : le garde contre le cycle d'import `analytics <-> cases` au lancement CLI (`python -m iryx.scripts.seed_data`) était masqué par `conftest.py`. Test sous-processus `test_cli_module_runs_in_clean_subprocess_without_import_cycle` ajouté.
- 2026-11-28 — [VG-4] `medium` (`patch`, pré-vérifié) : la réparation idempotente de `user.is_active`, `membership.role`, `case.status`, `case.description` et `case.created_by` n'était pas testée. Test `test_seed_repairs_deactivated_user_altered_role_and_closed_case` ajouté.


## Verification

**Commands:**
- `cd backend && uv run pytest -q tests/unit/test_seed_data.py` -- expected: vert.
- `cd backend && uv run ruff check src tests` -- expected: `All checks passed!`.
- `cd backend && uv run ruff format --check src tests` -- expected: fichiers inchangés/formattés.

**Results (2026-11-28):**
- `uv run pytest -q tests/unit/test_seed_data.py` → `11 passed`.
- `uv run pytest -q tests/unit/test_seed_data.py tests/unit/test_evidence_ingestion_task.py` → `25 passed`.
- `uv run ruff check src tests` → `All checks passed!`.
- `uv run ruff format --check src/iryx/scripts tests/unit/test_seed_data.py` → `4 files already formatted`.
- `uv run ruff format --check src tests` → échec sur 15 fichiers préexistants hors périmètre (`audit/triggers.py`, `core/exceptions.py`, `orchestrator/services.py`, `reporting/*`, plusieurs tests) ; aucun fichier de cette story n'est concerné.

**Results (2026-11-28, après reprise revue step-04) :**
- `cd backend && uv run pytest -q tests/unit/test_seed_data.py tests/unit/test_evidence_ingestion_task.py` → `30 passed in 12.74s` (16 tests dans `test_seed_data.py`, dont PrefetchParserTool, réparation fichier corrompu en lecture seule, réparation dérive user/rôle/dossier, CLI en sous-processus isolé, chemin staging blanc).
- `cd backend && uv run ruff check src tests` → `All checks passed!`.
- `cd backend && uv run ruff format --check src/iryx/scripts tests/unit/test_seed_data.py` → `4 files already formatted`.

**Matrix audit (2026-11-28):**
- Nominal → `test_seed_demo_data_nominal` (données + scellement), `test_main_returns_nonzero_on_database_error` et `test_main_returns_nonzero_when_staging_file_cannot_be_written` (échec explicite).
- Seconde exécution → `test_seed_is_idempotent_on_second_run` (aucun doublon/erreur SQL), `test_main_prints_credentials_and_password_warning` (résumé affiché).
- Preuve partiellement scellée → `test_seed_reseals_partially_sealed_evidence`, `test_seed_restores_missing_staging_file`, `test_main_returns_nonzero_when_staging_file_cannot_be_written`.
- Utilisateur existant email identique → `test_seed_repairs_invalid_demo_password` (réutilisation, réhash, aucun doublon).
- Staging non accessible → `test_main_returns_nonzero_when_staging_directory_is_unavailable`.
- Tous ces tests ont été exécutés et passent dans `uv run pytest -q tests/unit/test_seed_data.py`.

**Manual checks (if no CLI):**
- Inspecter la sortie du script : contient org, 4 utilisateurs, case, 3 preuves scellées, et l'avertissement mot de passe.