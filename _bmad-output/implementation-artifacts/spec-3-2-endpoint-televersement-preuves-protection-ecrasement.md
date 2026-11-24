---
title: "Story 3.2 : Endpoint de téléversement de preuves et protection contre l'écrasement"
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: '51d6f87455bc4ad13b4387fe259e6bd72828b653'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture.md'
  - '{project-root}/docs/03-modele-de-donnees.md'
  - '{project-root}/docs/04-securite-et-gates.md'
  - '{project-root}/docs/05-conventions-backend.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** L'API IRYX ne permet pas encore aux enquêteurs et analystes de téléverser des preuves numériques associées à un dossier (`Case`), ce qui bloque l'initiation du traitement forensique asynchrone et expose le système au risque d'écrasement accidentel de preuves homonymes.

**Approach:** Implémenter l'endpoint HTTP `POST /api/v1/cases/{case_id}/evidences` acceptant un fichier en multipart, enregistrer le flux entrant par morceaux de 64 Ko dans un répertoire de staging sous un UUID unique, créer les entités `Evidence` et `IngestionRun` (statut `pending`), émettre la tâche Celery `process_evidence_ingestion` vers Redis, et retourner HTTP 202 Accepted avec l'en-tête `Location` pointant vers l'URL de suivi d'ingestion.

## Boundaries & Constraints

**Always:**
- Protéger l'accès à l'endpoint avec la dépendance `verify_case_access` (retournant HTTP 404 si le dossier n'existe pas, et HTTP 403 si l'utilisateur n'appartient pas à l'organisation détentrice) avant toute écriture sur le disque.
- Exiger une authentification valide via `get_current_user` (HTTP 401 si non authentifié).
- Diffuser le flux de téléversement par morceaux (*chunks*) de 64 Ko (`UploadFile.read(65536)`) vers le disque temporaire de staging pour maîtriser la consommation mémoire sans saturer la RAM (ADR-0005, D-04).
- Attribuer à chaque fichier physique enregistré dans le staging un nom unique basé sur un UUID (ex. `{evidence_id}.bin`), garantissant l'impossibilité technique d'écraser un fichier existant.
- Rejeter tout fichier vide (taille 0 octet) avec HTTP 400 Bad Request et code d'erreur `EMPTY_FILE_ERROR` via l'exception `EmptyFileException`. Nettoyer immédiatement tout fichier staging temporaire créé.
- Rejeter tout fichier dépassant le plafond configuré `settings.max_evidence_size_gb` avec HTTP 413 Payload Too Large (`PAYLOAD_TOO_LARGE`) et purger le staging partiel.
- Détecter les fichiers homonymes (même `original_name` déjà présent dans le dossier `case_id`) : créer systématiquement une nouvelle entité `Evidence` avec un nouvel UUID et émettre un journal d'avertissement structuré de sécurité (docs/04 section 1.3) sans écraser le fichier préexistant.
- Créer l'entité `Evidence` (`id`, `case_id`, `original_name`, `file_size`, `imported_by=current_user.id`) et l'entité associée `IngestionRun` (`evidence_id`, `status=IngestionStatus.PENDING`, `progress=0`, `started_at=datetime.now(UTC)`).
- Publier la tâche Celery `process_evidence_ingestion.delay(str(evidence.id), str(staging_path))` dans Redis.
- Répondre HTTP 202 Accepted avec l'en-tête `Location: /api/v1/cases/{case_id}/evidences/{evidence.id}/ingestion-status` et le corps JSON `{"evidence_id": "...", "ingestion_run_id": "..."}`.

**Never:**
- Aucun calcul de hash cryptographique SHA-256 ni verrouillage `chmod 0440` dans cette story (responsabilité déléguée au worker Celery dans la Story 3.3).
- Aucune modification de schéma de base de données ni nouvelle migration Alembic (les tables `evidences` et `ingestion_runs` issues de la Story 3.1 sont déjà déployées).
- Aucun chargement intégral du fichier en mémoire vive (`file.read()` sans chunks).
- Aucun écrasement physique ni suppression logique ou physique de preuves préexistantes sur le volume de stockage.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Upload nominal | `POST /api/v1/cases/{case_id}/evidences` avec fichier multipart valide par membre autorisé | Fichier écrit en staging (`{evidence_id}.bin`), `Evidence` et `IngestionRun` créés, tâche Celery émise, HTTP 202 avec `Location` et corps `{evidence_id, ingestion_run_id}` | N/A |
| Fichier vide (0 octet) | Requête multipart avec fichier de taille 0 | Rejet immédiat HTTP 400 Bad Request avec code `EMPTY_FILE_ERROR`, nettoyage du fichier staging temporaire | `EmptyFileException` levée |
| Fichier manquant | Requête multipart sans champ `file` | Rejet HTTP 422 Unprocessable Content (FastAPI validation) | Handlé par `validation_exception_handler` |
| Preuve homonyme | Même `original_name` déjà présent dans le `case_id` | Nouvelle entité `Evidence` créée avec nouvel UUID distinct, pas d'écrasement, log warning d'intégrité tracé, HTTP 202 | N/A |
| Dossier inexistant | `case_id` inconnu dans la base | Rejet HTTP 404 Not Found avec code `CASE_NOT_FOUND`, aucun fichier staging écrit | `CaseNotFoundException` via `verify_case_access` |
| Utilisateur non membre | Utilisateur authentifié mais extérieur à l'organisation du dossier | Rejet HTTP 403 Forbidden avec code `FORBIDDEN`, aucun fichier staging écrit | `InsufficientPermissionsException` via `verify_case_access` |
| Utilisateur non authentifié | Requête sans en-tête `Authorization` | Rejet HTTP 401 Unauthorized avec code `UNAUTHORIZED` | Handlé par `get_current_user` |
| Dépassement taille max | Flux entrant dépassant `settings.max_evidence_size_gb` | Arrêt de la lecture, purge du fichier temporaire, rejet HTTP 413 | `PayloadTooLargeException` ou HTTP 413 |

</frozen-after-approval>

## Code Map

- `backend/src/iryx/core/config.py` -- Configuration de l'application : ajout de la propriété `evidence_staging_path` (par défaut `{evidence_storage_path}/staging`)
- `backend/src/iryx/core/exceptions.py` -- Hiérarchie d'exceptions : ajout de `EmptyFileException` (code `EMPTY_FILE_ERROR`, statut HTTP 400) et `PayloadTooLargeException` (code `PAYLOAD_TOO_LARGE`, statut HTTP 413)
- `backend/src/iryx/evidence/schemas.py` -- Schémas Pydantic : ajout de `EvidenceUploadResponse` (`evidence_id`, `ingestion_run_id`)
- `backend/src/iryx/evidence/tasks.py` -- Tâches Celery : définition de la tâche Celery `process_evidence_ingestion` (signature et publication, stub avant Story 3.3)
- `backend/src/iryx/evidence/services.py` -- Logique métier d'upload : streaming par chunks vers staging, détection d'homonymie, persistance `Evidence` et `IngestionRun`, envoi Celery
- `backend/src/iryx/evidence/router.py` -- Routeur API : endpoint `POST /api/v1/cases/{case_id}/evidences` avec injection `verify_case_access`, `get_current_user`, `get_db`
- `backend/src/iryx/main.py` -- Enregistrement du routeur `evidence_router` dans l'application FastAPI principale
- `backend/tests/unit/test_evidence_upload.py` -- Tests unitaires : validation streaming, gestion des fichiers vides, homonymie sans écrasement, exceptions
- `backend/tests/integration/test_evidence_api.py` -- Tests d'intégration API : scénarios nominaux HTTP 202, en-tête Location, isolation 403/404, auth 401, rejets 400/413

## Tasks & Acceptance

**Execution:**
- [x] `backend/src/iryx/core/config.py` -- Ajouter `evidence_staging_path` dans `Settings` avec fallback automatique vers `{evidence_storage_path}/staging` -- Paramétrage centralisé du répertoire de staging
- [x] `backend/src/iryx/core/exceptions.py` -- Ajouter les classes `EmptyFileException` et `PayloadTooLargeException` dans la hiérarchie unifiée -- Codes d'erreur standardisés conformes aux specs
- [x] `backend/src/iryx/evidence/schemas.py` -- Ajouter le schéma Pydantic `EvidenceUploadResponse` (`evidence_id: UUID`, `ingestion_run_id: UUID`) -- Contrat de réponse HTTP 202 typé
- [x] `backend/src/iryx/evidence/tasks.py` -- Créer la tâche Celery `process_evidence_ingestion(evidence_id: str, staging_path: str)` avec journalisation -- Déclaration de la tâche d'arrière-plan
- [x] `backend/src/iryx/evidence/services.py` -- Implémenter `EvidenceService` avec méthodes de streaming disque par morceaux de 64 Ko, détection d'homonymie et persistance transactionnelle -- Logique métier robuste et isolée
- [x] `backend/src/iryx/evidence/router.py` -- Déclarer le routeur `POST /api/v1/cases/{case_id}/evidences` avec code 202 et en-tête `Location` -- Exposition REST conforme OpenAPI
- [x] `backend/src/iryx/main.py` -- Enregistrer le routeur `evidence_router` sur l'application FastAPI -- Intégration globale des routes
- [x] `backend/tests/unit/test_evidence_upload.py` -- Écrire les tests unitaires du service d'upload et de la gestion des exceptions -- Couverture unitaire complète
- [x] `backend/tests/integration/test_evidence_api.py` -- Écrire les tests d'intégration complets de l'endpoint d'upload (nominal, homonymie, contrôle d'accès, fichier vide, volumétrie) -- Validation E2E du protocole

**Acceptance Criteria:**
- Given un analyste membre de l'organisation détentrice du dossier `{case_id}`, when il soumet une requête `POST /api/v1/cases/{case_id}/evidences` avec un fichier multipart valide, then le fichier est enregistré en staging sous un UUID unique, `Evidence` et `IngestionRun` sont créés, la tâche Celery est envoyée, et la réponse HTTP 202 contient le corps `{"evidence_id": "...", "ingestion_run_id": "..."}` et l'en-tête `Location: /api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status`.
- Given un fichier téléversé de taille 0 octet, when la requête est validée, then le serveur renvoie HTTP 400 Bad Request avec `{"error": {"code": "EMPTY_FILE_ERROR", "message": "..."}}` et aucun artefact orphelin ne subsiste sur le disque.
- Given une preuve téléversée portant le même nom qu'un fichier existant dans le dossier, when le téléversement réussit, then une nouvelle entité `Evidence` avec un UUID distinct est créée, aucun fichier existant n'est écrasé, et un avertissement d'audit est consigné dans les logs.
- Given un utilisateur non membre ou un `case_id` inconnu, when la requête de téléversement est émise, then la dépendance `verify_case_access` rejette la requête en HTTP 403 ou 404 avant toute création de fichier en staging.

## Implementation Notes

- Implémentation du streaming multipart par blocs de 64 Ko (`CHUNK_SIZE = 65536`) dans `EvidenceService` écrivant directement dans `evidence_staging_path/{evidence_id}.bin`.
- Contrôle de cohérence et conformité stricte des exceptions HTTP : `EmptyFileException` (HTTP 400 `EMPTY_FILE_ERROR`) et `PayloadTooLargeException` (HTTP 413 `PAYLOAD_TOO_LARGE`).
- Protection contre l'écrasement physique via nommage UUID unique sur disque et détection d'homonymie avec émission de log warning d'audit.
- Déclaration et dispatch de la tâche Celery `process_evidence_ingestion.delay(str(evidence.id), str(staging_path))`.
- Ajout de la dépendance `python-multipart` et validation complète par 15 tests unitaires et d'intégration dédiés. Suite globale (284 tests) passée à 100%.

## Spec Change Log

## Review Triage Log

| Ref | Source | Verdict | Evidence / Justification | Route |
|-----|--------|---------|--------------------------|-------|
| F01 | edge-case-hunter / blind-hunter / verification-gap | medium | Si le courtier Celery/Redis est inaccessible, `IngestionRun` reste bloqué à `pending` indéfiniment ; marquer `IngestionRun.status = FAILED`, horodater `completed_at` et consigner `error_message`. | patch |
| F02 | edge-case-hunter / blind-hunter | medium | Absence de normalisation des chemins Windows (`\`) et validation de longueur (>255 caractères) sur `file.filename` ; nettoyer les séparateurs et tronquer/valider pour éviter un `DataError` SQL. | patch |
| F03 | edge-case-hunter / blind-hunter | low | Absence de `await file.close()` dans un bloc `finally` pour libérer explicitement les descripteurs de fichiers temporaires de l'upload. | patch |
| F04 | edge-case-hunter / blind-hunter | low | Fichier avec nom vide ou constitué uniquement de séparateurs/espaces ; normaliser `original_name` avec fallback `"evidence.bin"`. | patch |
| F05 | blind-hunter | low | Fichier de staging orphelin si une erreur DB survient pendant la détection d'homonyme avant le bloc de transaction ; englober dans un `try...finally`. | patch |
| F06 | blind-hunter | low | Valeurs par défaut `= None` sur les dépendances obligatoires FastAPI dans `router.py` ; supprimer `= None` pour respecter le typage strict du projet. | patch |
| F07 | blind-hunter | false | Contrôle RBAC restreint aux rôles opérationnels : la spécification et l'acceptation imposent explicitement l'injection directe de `verify_case_access`. | rejet |
| F08 | blind-hunter | false | Contrôle du statut du dossier (`CaseStatus.CLOSED`) : hors périmètre de la Story 3.2 et non requis par les critères d'acceptation. | rejet |
| F09 | blind-hunter | low | Inclusion des identifiants des preuves préexistantes (`conflicting_evidence_ids`) dans le log d'avertissement d'homonymie pour un audit plus précis. | patch |
| F10 | blind-hunter | false | I/O bloquante sur fichier staging : les écritures par blocs de 64 Ko utilisent la mise en cache noyau standard sans nécessiter de bibliothèque asynchrone non approuvée. | rejet |
| F11 | blind-hunter | false | Calcul SHA-256 en une seule passe : formellement exclu de la Story 3.2 par les contraintes (sanctuarisé dans la Story 3.3). | rejet |
| F12 | blind-hunter | low | Alignement du statut de la story dans `sprint-status.yaml` : passer `3-2` à `review`. | patch |
| F13 | verification-gap | medium | Dans `test_evidence_api.py`, les tests 401/403/404 vérifient `temp_staging` sans patcher `get_settings` avec `integration_settings`. | patch |
| F14 | verification-gap | low | Dans `test_evidence_upload.py`, `test_upload_evidence_nominal` ne vérifie pas les appels unitaires successifs à `file.read(CHUNK_SIZE)`. | patch |

## Design Notes

### Streaming et Staging
Pour respecter ADR-0005 et prévenir l'épuisement de la mémoire sur des preuves massives, l'écriture sur le disque s'opère de manière itérative :
```python
buffer_size = 65536  # 64 Ko
total_bytes = 0
with open(staging_file_path, "wb") as destination:
    while chunk := await file.read(buffer_size):
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise PayloadTooLargeException()
        destination.write(chunk)
```
Si `total_bytes == 0`, le fichier temporaire est supprimé (`staging_file_path.unlink(missing_ok=True)`) et `EmptyFileException` est levée.

### Traçabilité des Preuves Homonymes
La recherche d'homonymes s'effectue via une requête SQLAlchemy `select(Evidence).where(Evidence.case_id == case_id, Evidence.original_name == file.filename)`. Si une ou plusieurs preuves existent déjà avec ce nom, un log d'avertissement structuré est émis :
```python
logger.warning(
    "Téléversement d'une preuve homonyme dans le dossier",
    extra={"context": {"case_id": str(case_id), "original_name": file.filename, "new_evidence_id": str(new_evidence_id)}}
)
```

## Verification

**Commands:**
- `uv run --directory backend pytest tests/unit/test_evidence_upload.py tests/integration/test_evidence_api.py` -- expected: Tous les tests unitaires et d'intégration de l'upload passent avec succès (100% passés)
- `uv run --directory backend ruff check src tests` -- expected: 0 erreur, 0 avertissement
- `uv run --directory backend pytest` -- expected: L'ensemble de la suite de tests (267+ tests) passe sans régression
