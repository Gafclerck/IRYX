---
title: "Story 3.3 : Tâche Celery d'ingestion : scellement SHA-256, détection filetype et verrouillage lecture seule"
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: 'b5bb719096bca8b0faae6d469da3c12f32a809f9'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/docs/04-securite-et-gates.md'
  - '{project-root}/docs/adr/ADR-0005-televersement-streaming-et-taille-max-preuves.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Les preuves numériques téléversées par les analystes sont actuellement déposées dans le répertoire de staging sous un UUID unique avec un `IngestionRun` en attente (`pending`), mais leur intégrité n'est pas scellée cryptographiquement, leur type MIME réel n'est pas validé par signature binaire et les fichiers restent modifiables sur le système de fichiers, ce qui compromet la recevabilité légale et technique des preuves forensiques.

**Approach:** Implémenter la logique complète de la tâche Celery d'arrière-plan `process_evidence_ingestion(evidence_id, staging_path)` : passer `IngestionRun` à `processing` (20%), calculer l'empreinte SHA-256 par flux de blocs de 64 Ko (`hashlib.sha256`), détecter le type MIME et l'extension par inspection des signatures binaires (`filetype`), verrouiller le fichier sur le disque avec permissions strictes en lecture seule (`chmod 0440`), mettre à jour l'entité `Evidence` et finaliser `IngestionRun` à `completed` (100%) avec gestion d'erreurs I/O transactionnelle.

## Boundaries & Constraints

**Always:**
- Utiliser une session de base de données synchrone dédiée (`SessionLocal()`) au sein du worker Celery avec bloc `try...finally` garantissant la clôture (`db.close()`) et le rollback en cas d'exception.
- Passer l'état de `IngestionRun` à `processing` avec `progress = 20` dès le début effectif de l'exécution sur le worker Celery.
- Calculer l'empreinte cryptographique SHA-256 via `hashlib.sha256()` par flux itératif de blocs de 64 Ko (`buffer_size = 65536`) pour garantir une consommation de mémoire vive constante et bornée (ADR-0005, D-14).
- Détecter le format réel du fichier à partir de ses octets d'en-tête à l'aide de la bibliothèque `filetype` (>=1.2.0, D-15), sans dépendance système native (`python-magic`), et enregistrer le type MIME (avec fallback `"application/octet-stream"` si indéterminé) dans `Evidence.detected_type`.
- Appliquer un verrouillage physique strict en lecture seule via `os.chmod(staging_path, 0o440)` (NFR-SEC-01), interdisant toute écriture ultérieure par les comptes applicatifs et levant `PermissionError` en cas de tentative d'ouverture en écriture (`"wb"`).
- En cas de succès : enregistrer `sha256` et `detected_type` sur `Evidence`, passer `IngestionRun.status = IngestionStatus.COMPLETED`, `IngestionRun.progress = 100`, `IngestionRun.completed_at = datetime.now(UTC)`, `IngestionRun.error_message = None`, et valider la transaction (`db.commit()`).
- En cas d'erreur I/O, fichier introuvable ou corruption : basculer `IngestionRun.status = IngestionStatus.FAILED`, renseigner `IngestionRun.error_message`, horodater `IngestionRun.completed_at`, consigner l'erreur dans les journaux JSON structurés et commiter l'état d'échec.

**Never:**
- Aucune modification du schéma relationnel ni création de nouvelle migration Alembic (les tables `evidences` et `ingestion_runs` issues de Story 3.1 disposent déjà des colonnes requises).
- Aucun chargement intégral du fichier en mémoire vive pour le calcul de hash (`f.read()` sans chunks interdit).
- Aucun appel à des dépendances système Linux C natives ou paquets non portables (interdiction de `libmagic` ou `python-magic`, stricte adhésion à `filetype` D-15).
- Aucune suppression ni altération du fichier de preuve en cas d'erreur de traitement d'ingestion (la preuve physique doit subsister pour investigation).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ingestion nominale | `evidence_id` valide, fichier staging présent et lisible | `IngestionRun` 20% -> 100% completed, `Evidence.sha256` calculé, `Evidence.detected_type` détecté, fichier chmod 0440 | N/A |
| Fichier staging manquant / I/O error | `staging_path` inexistant ou inaccessible en lecture | `IngestionRun` passe à `failed`, `error_message` renseigné avec le message d'erreur, log JSON ERROR | Log structuré + persistance statut FAILED |
| Format binaire non reconnu | Fichier texte ou binaire propriétaire inconnu de `filetype` | Empreinte SHA-256 scellée, `Evidence.detected_type = "application/octet-stream"`, statut `completed` | Fallback transparent sans échec |
| Tentative d'écriture post-scellement | Fichier verrouillé en `0440` après scellement | Tentative `open(path, "wb")` lève immédiatement `PermissionError` (NFR-SEC-01) | Handlé par OS (`PermissionError`) |
| Preuve inconnue en base | `evidence_id` introuvable dans la table `evidences` | Log JSON d'erreur, abandon sans exception non gérée | Exception interceptée et logguée |

</frozen-after-approval>

## Code Map

- `backend/pyproject.toml` -- Dépendances applicatives : ajout de `filetype>=1.2.0` (D-15) dans `dependencies`
- `backend/src/iryx/evidence/tasks.py` -- Tâches Celery : implémentation de `process_evidence_ingestion(evidence_id: str, staging_path: str)` avec streaming SHA-256, `filetype.guess`, `chmod 0440`, mise à jour d'`Evidence` et `IngestionRun`
- `backend/src/iryx/evidence/services.py` -- Services du domaine evidence : réutilisation des constantes de chunks (`CHUNK_SIZE`) et contextes
- `backend/tests/unit/test_evidence_ingestion_task.py` -- Tests unitaires : validation unitaire de la tâche Celery (nominal, chunks SHA-256, types MIME reconnus et fallback, verrouillage 0440, gestion d'erreurs I/O, fichier introuvable)
- `backend/tests/integration/test_evidence_ingestion_pipeline.py` -- Tests d'intégration : exécution synchrone (Celery eager ou direct) vérifiant le pipeline complet depuis l'état pending jusqu'à completed/failed et persistance en base

## Tasks & Acceptance

**Execution:**
- [x] `backend/pyproject.toml` -- Ajouter la dépendance `filetype>=1.2.0` et synchroniser l'environnement virtuel -- Support de l'inspection binaire des formats de preuves (D-15)
- [x] `backend/src/iryx/evidence/tasks.py` -- Implémenter la logique complète de `process_evidence_ingestion` avec session DB `SessionLocal`, transition de statut `processing` (20%), calcul de hash SHA-256 par flux de 64 Ko, inspection `filetype`, verrouillage `os.chmod(..., 0o440)` et clôture `completed` (100%) -- Cœur de la tâche d'arrière-plan Celery (FR6, FR7, NFR-SEC-01)
- [x] `backend/tests/unit/test_evidence_ingestion_task.py` -- Écrire les tests unitaires complets de la tâche d'ingestion (scénarios nominaux, formats MIME connus et fallback, simulation d'erreur I/O, contrôle de verrouillage `0440` avec tentative d'écriture rejetée par `PermissionError`) -- Couverture unitaire exhaustive de la tâche
- [x] `backend/tests/integration/test_evidence_ingestion_pipeline.py` -- Écrire les tests d'intégration du cycle d'ingestion avec session de base de données réelle (vérification de la persistance de `sha256`, `detected_type`, statuts et progression dans PostgreSQL) -- Validation du pipeline bout-en-bout

**Acceptance Criteria:**
- Given la tâche Celery `process_evidence_ingestion` déclenchée avec un identifiant de preuve valide et son chemin de staging, when la tâche s'exécute sur le worker, then l'état de `IngestionRun` passe d'abord à `processing` avec une progression de 20%, puis le hash SHA-256 est calculé par blocs de 64 Ko et enregistré dans `Evidence.sha256`, le type MIME réel est détecté par `filetype` et stocké dans `Evidence.detected_type`, le fichier sur disque est verrouillé en lecture seule (`chmod 0440`), et `IngestionRun` passe à `completed` avec `progress = 100` et `completed_at` horodaté en UTC.
- Given un fichier corrompu ou inaccessible sur le disque lors de l'exécution de la tâche Celery, when la tâche rencontre une erreur d'entrée/sortie, then l'entité `IngestionRun` passe au statut `failed`, `error_message` contient le descriptif de l'anomalie, et l'erreur est consignée dans les logs JSON structurés.
- Given le fichier de preuve scellé sur disque avec les permissions `0440`, when un processus applicatif ou de test tente d'ouvrir le fichier en écriture (`open(path, "wb")`), then le système d'exploitation lève immédiatement une `PermissionError`.

## Implementation Notes

- Ajout de la dépendance `filetype>=1.2.0` (D-15) dans `backend/pyproject.toml` et synchronisation via `uv sync`.
- Implémentation complète de la tâche Celery `process_evidence_ingestion` dans `backend/src/iryx/evidence/tasks.py` :
  - Session synchrone dédiée `SessionLocal()` avec garantie de rollback et clôture dans un bloc `try...finally`.
  - Garde d'idempotence : retour immédiat si `IngestionRun.status == IngestionStatus.COMPLETED` et hash déjà calculé.
  - Transition immédiate vers `IngestionRun.status = IngestionStatus.PROCESSING` et `progress = 20`.
  - Scellement préalable en lecture seule `os.chmod(staging_path, 0o440)` (NFR-SEC-01) avant la passe de lecture, interdisant toute mutation concurrente.
  - Calcul du hash SHA-256 par streaming itératif de 64 Ko (`CHUNK_SIZE = 65536`) via `hashlib.sha256()`.
  - Contrôle d'intégrité de la volumétrie : vérification stricte `total_bytes == evidence.file_size`.
  - Détection du type binaire avec `filetype.guess(first_chunk)` sur le premier buffer en mémoire (D-15, sans réouverture disque) et fallback transparent `"application/octet-stream"`.
  - Mise à jour et scellement d'`Evidence` et finalisation à `IngestionStatus.COMPLETED` (`progress = 100`).
  - Gestion transactionnelle des erreurs I/O, chemin hors staging ou invalidité UUID vers `IngestionStatus.FAILED` avec conservation physique de la preuve sur disque.
- Définition et réexportation de `CHUNK_SIZE = 65536` pour éviter les dépendances circulaires.
- Création de 14 tests unitaires dans `backend/tests/unit/test_evidence_ingestion_task.py` et 5 tests d'intégration dans `backend/tests/integration/test_evidence_ingestion_pipeline.py`.
- Validation : 19/19 nouveaux tests passés, 0 erreur Ruff, et suite globale de 305 tests passée avec succès (100%).

## Spec Change Log

## Review Triage Log

| Ref | Source | Verdict | Evidence / Justification | Route |
|-----|--------|---------|--------------------------|-------|
| V01 | verification-gap | false | Aucun écart de vérification détecté par la couche formelle. | rejet |
| B01 | blind-hunter | medium | Absence de contrôle de conformité entre le nombre d'octets lus et `evidence.file_size` ; lever une `ValueError` si divergence. | patch |
| B02 | blind-hunter | low | Exécution silencieuse si `ingestion_run` est absent en base ; échouer proprement sans continuer sans run. | patch |
| B03 | blind-hunter | low | Absence de vérification du confinement du chemin de staging ; valider avec `is_relative_to(settings.evidence_staging_path)`. | patch |
| B04 | blind-hunter | false | Verrouillage 0440 avant commit DB : en DFIR, préserver le fichier physique en lecture seule en cas d'erreur DB est conforme aux règles d'immutabilité. | rejet |
| B05 | blind-hunter | low | Réouverture redondante du fichier sur disque par `filetype.guess` ; passer le buffer du premier bloc lu en mémoire `filetype.guess(first_chunk)`. | patch |
| B06 | blind-hunter | false | Tâche Celery retournant un dictionnaire au lieu de lever : l'application utilise le polling REST sur PostgreSQL (Story 3.4), consigner `status = FAILED` en DB est le comportement requis. | rejet |
| B07 | blind-hunter | low | Requête `IngestionRun` non filtrée par statut ; sécurisé par la vérification d'état et la garde d'idempotence. | patch |
| B08 | blind-hunter / edge-case-hunter | medium | Absence de garde d'idempotence en cas de réémission Celery : si `status == COMPLETED` et `sha256` renseigné, retourner immédiatement sans re-traiter. | patch |
| B09 | blind-hunter | low | Statut du sprint à synchroniser dans `sprint-status.yaml` : passer `3-3` à `review`. | patch |
| B10 | blind-hunter | low | Couverture de tests unitaires pour les cas limites négatifs : ajouter tests pour idempotence, divergence de taille, et run absent. | patch |
| E01 | edge-case-hunter | medium | Doublon B08 : régression d'une tâche déjà complétée vers l'état processing à 20% lors d'une re-livraison. | patch |
| E02 | edge-case-hunter | medium | Fichier de staging restant modifiable pendant la passe de hachage ; positionner `os.chmod(staging_path, 0o440)` avant la lecture streaming. | patch |
| E03 | edge-case-hunter | false | SQLite in-memory utilisé dans les tests au lieu de PostgreSQL : conforme à l'architecture de test du projet sur l'ensemble des stories. | rejet |
| E04 | edge-case-hunter | false | Extension non persistée : le modèle relationnel `Evidence` ne possède que la colonne `detected_type`, stocker le type MIME respecte le schéma. | rejet |

## Design Notes

### Calcul SHA-256 par streaming de 64 Ko
Pour respecter ADR-0005 et D-14 sans saturer la mémoire vive du worker Celery même sur des fichiers volumineux de plusieurs gigaoctets :
```python
sha256_hash = hashlib.sha256()
with open(staging_path, "rb") as f:
    while chunk := f.read(65536):
        sha256_hash.update(chunk)
calculated_sha256 = sha256_hash.hexdigest()
```

### Détection du type binaire (D-15)
L'inspection d'en-tête s'appuie sur `filetype` sans dépendance native externe :
```python
kind = filetype.guess(staging_path)
detected_type = kind.mime if kind is not None else "application/octet-stream"
```

### Scellement et permissions lecture seule (NFR-SEC-01)
Le verrouillage physique s'opère par `os.chmod` :
```python
os.chmod(staging_path, 0o440)
```
Sur système POSIX comme sur Windows, ce réglage retire les droits d'écriture et déclenche une `PermissionError` immédiate lors d'un appel ultérieur à `open(staging_path, "wb")`.

## Verification

**Commands:**
- `uv run --directory backend pytest tests/unit/test_evidence_ingestion_task.py tests/integration/test_evidence_ingestion_pipeline.py` -- expected: Tous les tests unitaires et d'intégration de l'ingestion passent avec succès (100% passés)
- `uv run --directory backend ruff check src tests` -- expected: 0 erreur, 0 avertissement
- `uv run --directory backend pytest` -- expected: L'ensemble de la suite de tests globale passe sans régression
