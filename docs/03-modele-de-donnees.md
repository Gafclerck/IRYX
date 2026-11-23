# 03 - Modèle de Données : Entités, Schémas et Invariants
 
---
 
## 1. Entités et champs clés
 
Les noms d'entités et de champs ci-dessous sont intangibles et partagés sans divergence entre la couche API, l'ORM SQLAlchemy 2.x, les migrations Alembic et les schémas Pydantic.
 
### 1.1 `Organization`
Représente l'entité cliente ou le département de sécurité titulaire du compte.
- `id` : UUID, clé primaire.
- `name` : String, nom de l'organisation.
- `created_at` : DateTime UTC.
- `updated_at` : DateTime UTC.
 
### 1.2 `User`
Utilisateur enregistré accédant à la plateforme.
- `id` : UUID, clé primaire.
- `email` : String, unique, indexé.
- `hashed_password` : String (hachage argon2 via pwdlib).
- `is_active` : Boolean, indicateur de compte actif.
- `created_at` : DateTime UTC.
- `updated_at` : DateTime UTC.
 
### 1.3 `Membership`
Association entre un utilisateur et une organisation avec attribution de rôle.
- `id` : UUID, clé primaire.
- `organization_id` : UUID, clé étrangère vers `Organization.id`.
- `user_id` : UUID, clé étrangère vers `User.id`.
- `role` : Enum (`admin`, `analyst`, `investigator`, `viewer`).
- `created_at` : DateTime UTC.
 
### 1.4 `Case`
Dossier d'investigation numérique ou d'analyse de fraude.
- `id` : UUID, clé primaire.
- `organization_id` : UUID, clé étrangère vers `Organization.id`.
- `title` : String, intitulé du dossier.
- `status` : Enum (`open`, `in_progress`, `review`, `closed`).
- `description` : Text, contexte de l'incident.
- `created_by` : UUID, clé étrangère vers `User.id`.
- `created_at` : DateTime UTC.
- `updated_at` : DateTime UTC.
 
### 1.5 `Evidence`
Preuve numérique brute importée dans un dossier.
- `id` : UUID, clé primaire.
- `case_id` : UUID, clé étrangère vers `Case.id`.
- `original_name` : String, nom du fichier d'origine.
- `file_size` : BigInteger, taille en octets.
- `sha256` : String(64), empreinte cryptographique SHA-256 scellée.
- `detected_type` : String, type MIME / format identifié via signature binaire.
- `imported_by` : UUID, clé étrangère vers `User.id`.
- `created_at` : DateTime UTC.
 
### 1.6 `IngestionRun`
Opération asynchrone de calcul d'empreinte, de contrôle d'intégrité et de pré-analyse de la preuve.
- `id` : UUID, clé primaire.
- `evidence_id` : UUID, clé étrangère vers `Evidence.id`.
- `status` : Enum (`pending`, `processing`, `completed`, `failed`).
- `progress` : Integer (0 à 100).
- `error_message` : Text, nullable, description de l'incident d'ingestion.
- `started_at` : DateTime UTC.
- `completed_at` : DateTime UTC, nullable.
 
### 1.7 `Observation`
Fait technique unitaire normalisé extrait d'une preuve.
- `id` : UUID, clé primaire.
- `case_id` : UUID, clé étrangère vers `Case.id`.
- `source_id` : UUID, clé étrangère vers `Evidence.id`.
- `tool_name` : String, nom de l'outil générateur.
- `tool_execution_id` : UUID, clé étrangère vers `ToolExecution.id`.
- `normalized_content` : JSONB, charge utile normalisée (attributs, identifiants, valeurs).
- `timestamp_utc` : DateTime UTC, nullable, horodatage extrait de l'artefact.
- `source_location` : String, chemin interne, numéro d'enregistrement ou offset dans la source.
 
### 1.8 `ToolExecution`
Trace auditable de chaque appel d'outil opéré via la Gateway.
- `id` : UUID, clé primaire.
- `case_id` : UUID, clé étrangère vers `Case.id`.
- `tool_name` : String, outil appelé.
- `tool_version` : String, version figée de l'outil exécuté.
- `agent_role` : String, rôle de l'agent émetteur (`Planner`, `Executor`, `Analyst`).
- `parameters` : JSONB, paramètres d'appel validés.
- `result_sha256` : String(64), empreinte de l'intégralité du résultat brut produit.
- `duration_ms` : Integer, temps d'exécution en millisecondes.
- `status` : Enum (`success`, `error`, `timeout`).
- `created_at` : DateTime UTC.
 
### 1.9 `InvestigationRun`
Session globale d'exécution d'une enquête orchestrée par LangGraph.
- `id` : UUID, clé primaire.
- `case_id` : UUID, clé étrangère vers `Case.id`.
- `status` : Enum (`pending`, `running`, `paused`, `completed`, `failed`).
- `current_phase` : Enum (`triage`, `planning`, `execution`, `analysis`, `verification`, `reporting`).
- `validated_plan` : JSONB, plan d'étapes validé lors de la porte H1.
- `iteration_count` : Integer, compteur d'itérations courantes.
- `error_count` : Integer, nombre d'erreurs d'exécution enregistrées.
- `started_at` : DateTime UTC.
- `updated_at` : DateTime UTC.
 
### 1.10 `Phase`
Sous-étape d'une session d'investigation.
- `id` : UUID, clé primaire.
- `investigation_run_id` : UUID, clé étrangère vers `InvestigationRun.id`.
- `phase_name` : String, nom de la phase.
- `status` : Enum (`pending`, `active`, `completed`, `failed`).
- `started_at` : DateTime UTC.
- `completed_at` : DateTime UTC, nullable.
 
### 1.11 `Finding`
Conclusion d'investigation formulée par l'analyste ou les agents.
- `id` : UUID, clé primaire.
- `case_id` : UUID, clé étrangère vers `Case.id`.
- `title` : String, intitulé concis du constat.
- `severity` : Enum (`low`, `medium`, `high`, `critical`).
- `confidence` : Enum (`low`, `medium`, `high`).
- `finding_type` : Enum (`fact`, `inference`, `hypothesis`).
- `status` : Enum (`proposed`, `validated`, `rejected`).
- `observation_refs` : ARRAY(UUID), liste d'identifiants d'entités `Observation` justifiant le finding.
- `tool_execution_refs` : ARRAY(UUID), liste d'identifiants `ToolExecution` associés.
- `created_by` : UUID, clé étrangère vers `User.id` ou identifiant système.
- `created_at` : DateTime UTC.
 
### 1.12 `Report`
Document de synthèse d'incident généré et scellé.
- `id` : UUID, clé primaire.
- `case_id` : UUID, clé étrangère vers `Case.id`.
- `format` : Enum (`markdown`, `pdf`, `json`).
- `sha256` : String(64), empreinte cryptographique du rapport compilé.
- `created_at` : DateTime UTC.
- `status` : Enum (`draft`, `validated`, `exported`).
 
### 1.13 `AuditEvent`
Journalisation de sécurité immuable.
- `id` : UUID, clé primaire.
- `case_id` : UUID, nullable (pour actions globales), clé étrangère vers `Case.id`.
- `actor_id` : UUID, utilisateur ou agent à l'origine de l'action.
- `action` : String, code de l'action (ex. `CASE_ACCESS`, `EVIDENCE_UPLOAD`, `GATE_H1_VALIDATE`).
- `target_type` : String, type d'entité visée (`Case`, `Evidence`, `ToolExecution`, etc.).
- `target_id` : UUID, identifiant de l'entité visée.
- `created_at` : DateTime UTC.
- `payload_hash` : String(64), empreinte cryptographique de la charge utile de l'événement.
- `details` : JSONB, métadonnées contextuelles de sécurité (IP, identifiant de session).
 
---
 
## 2. Invariants et règles de cohérence du modèle
 
1. **Intégrité référentielle absolue des Findings** :
   Un `Finding` ne peut être créé ou validé que si chaque identifiant présent dans `observation_refs` et `tool_execution_refs` existe préalablement dans la base de données au sein du même `Case`. Le composant `Verifier` rejette immédiatement tout finding orphelin.
2. **Chronologie exclusivement dérivée des Observations** :
   Aucune entrée temporelle ne peut être forgée ou éditée manuellement dans la timeline d'un dossier. La chronologie est une vue matérialisée ou calculée par projection des champs `timestamp_utc` des entités `Observation` confirmées.
3. **Immutabilité stricte du journal d'audit (`AuditEvent`)** :
   La table `AuditEvent` fonctionne exclusivement en mode ajout seul (append-only). Tout déclencheur ou règle de base bloque toute tentative de modification (`UPDATE`) ou de suppression (`DELETE`).
 
---
 
Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
