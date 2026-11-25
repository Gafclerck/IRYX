# 14 - Contrat et Simulation : Stratégie OpenAPI et Découplage

---

## 1. Principes directeurs de l'approche Contrat d'abord (Contract-First)

Afin de permettre un développement front-end rigoureux et parfaitement synchronisé avec les livrables du back-end, le projet applique les principes fondamentaux suivants :

1. **Source unique de vérité pour les types** :
   Le contrat OpenAPI publié par le back-end constitue l'unique source de définition des types et interfaces de données. Le front-end s'interdit formellement de déclarer ou de maintenir des types d'API manuellement.
2. **Couche de simulation déterministe (MSW)** :
   Une couche d'interception et de simulation de requêtes réseau, alimentée directement par les définitions et schémas du contrat OpenAPI, permet de développer et tester l'ensemble des parcours applicatifs avant la disponibilité effective du serveur back-end.
3. **Bascule progressive et étanche par épic** :
   Le passage des requêtes simulées aux appels réseau réels s'effectue épic par épic, au fur et à mesure que les modules back-end sont stabilisés, testés et figés.
4. **Indépendance de la planification** :
   L'absence temporaire du fichier de spécification OpenAPI ne constitue pas un obstacle pour la phase de planification (rédaction du PRD front, cadrage de l'architecture, découpage des épics et spécification des écrans).

---

## 2. Statut actuel du contrat OpenAPI

À la date de formalisation de ce document, le fichier de spécification OpenAPI existe sous forme de brouillon (`docs/contrat/openapi.json`), sans routes d'authentification finalisées :

- **Statut opérationnel** : **DISPONIBLE (BROUILLON)** pour les routes de dossiers, preuves et orchestration ; routes d'authentification en attente côté back-end.
- **Emplacement du fichier** : `docs/contrat/openapi.json` (types TypeScript générés via `npm run generate:api` vers `frontend/src/api/schema.ts`).
- **Contrat cible d'authentification** : `docs/contrat/auth-contrat-cible.yaml` (décrit en prose et en schéma d'après `docs/proposals/PROPOSITION-auth-back-E1.md`).
- **Conséquence sur le front-end** : Les routes présentes dans `openapi.json` disposent de types générés automatiquement ; les routes d'authentification sont simulées via MSW à partir de `auth-contrat-cible.yaml`.

### 2.1 Référentiel des routes d'authentification simulées (Stories F1.2, F1.4 et F1.5)

Les trois routes d'authentification ci-dessous sont interceptées et simulées par Mock Service Worker (MSW) dans `frontend/src/test/mocks/handlers.ts` :

| Méthode et route HTTP | Description opérationnelle | Mention de statut |
|---|---|---|
| `POST /api/v1/auth/login` | Authentification analyste, délivrance jeton Bearer (15 min) et cookie refresh (7 j) | simulée, contrat cible : auth-contrat-cible.yaml |
| `POST /api/v1/auth/refresh` | Renouvellement silencieux du jeton d'accès via cookie httpOnly | simulée, contrat cible : auth-contrat-cible.yaml |
| `POST /api/v1/auth/logout` | Déconnexion explicite et suppression du cookie httpOnly (Max-Age=0) | simulée, contrat cible : auth-contrat-cible.yaml |

### 2.2 Référentiel des routes protégées simulées (Stories F1.3, F1.5, F1.6, F1.7, F2.1, F2.2, F3.1, F3.2, F3.3, F4.1 et F4.2)

Les routes protégées ci-dessous sont interceptées et simulées par Mock Service Worker (MSW) dans `frontend/src/test/mocks/handlers.ts` pour tester l'injection de l'en-tête `Authorization: Bearer <token>`, la détection d'expiration (HTTP 401), la pagination, la recherche, la création en modale, la consultation et l'édition du contexte, l'évolution du statut du dossier, ainsi que le téléversement et l'inventaire de preuves numériques avec suivi de progression et de l'état d'ingestion. La story F4.2 ajoute l'arbitrage formel de la porte H1 :

| Méthode et route HTTP | Description opérationnelle | Mention de statut |
|---|---|---|
| `GET /api/v1/auth/me` | Profil utilisateur connecté (schéma UserResponse préliminaire sans nom ni organisation), requiert l'en-tête Authorization: Bearer en mémoire | simulée, contrat cible : openapi.json (à réaligner pour identité F1.5) |
| `GET /api/v1/cases` | Consultation paginée et recherche des dossiers (Story F1.6), avec paramètres limit, offset, search, requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json |
| `POST /api/v1/cases` | Création d'un nouveau dossier d'investigation en modale (Story F1.7), validation Zod avant envoi, champs titre, date de l'incident, type d'incident, systèmes concernés et description, requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json |
| `GET /api/v1/cases/{case_id}` | Consultation unitaire du contexte d'un dossier d'investigation (Story F2.1), requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json |
| `PATCH /api/v1/cases/{case_id}` | Mise à jour en ligne du titre et de la description d'un dossier (Story F2.1), validation Zod avant envoi, requiert l'en-tête Authorization: Bearer | simulée, contrat cible : à réaligner |
| `PATCH /api/v1/cases/{case_id}/status` | Évolution du statut global du dossier selon la matrice de transition stricte (Story F2.2), validation Zod avant envoi, requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json |
| `POST /api/v1/cases/{case_id}/evidences` | Dépôt et téléversement de preuves numériques avec progression (Story F3.1), flux multipart, requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json |
| `GET /api/v1/cases/{case_id}/evidences` | Consultation paginée de l'inventaire des preuves d'un dossier (Story F3.2), avec pagination limit et offset, requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json |
| `GET /api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status` | Consultation de l'état d'ingestion d'une preuve et scrutation avec Retry-After (Story F3.2), requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json |
| `GET /api/v1/cases/{case_id}/evidences/{evidence_id}` | Consultation des métadonnées détaillées d'une preuve pour le panneau latéral d'inspection (Story F3.3), empreinte SHA-256 intégrale, historique d'ingestion, observations et troncature DP-04, requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json (champs d'enrichissement à réaligner) |
| `GET /api/v1/cases/{case_id}/investigations` | Résolution de la session d'investigation courante d'un dossier pour la consultation du plan (Story F4.1), requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json |
| `GET /api/v1/cases/{case_id}/investigations/{run_id}/plan` | Consultation en lecture seule de la séquence proposée par le Planner (Story F4.1), scrutation avec Retry-After: 3 (ADR-0008), requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json (agent assigné et état vide à réaligner) |
| `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h1` | Arbitrage formel de la porte H1 (Story F4.2) : validation, retrait d'étapes ou refus motivé après confirmation explicite, requiert l'en-tête Authorization: Bearer | **simulée, contrat cible : openapi.json** |

#### Règle documentée pour les requêtes sans jeton (Story F1.3)
Lorsqu'aucun jeton d'accès n'est présent en mémoire vive volatile (état initial ou purge), la requête vers un endpoint protégé est transmise sans en-tête `Authorization`. Le serveur récepteur ou l'intercepteur de simulation MSW renvoie alors un code HTTP 401, déclenchant le signal interne « jeton expiré ou absent ». Emplacement réservé pour la politique d'inactivité de l'analyste : à décider (C4).

### 2.3 Protocole de renouvellement silencieux et éviction (Story F1.4)

Conformément à l'ADR-0011, aux décisions D1, D3, D6 et DP-06 :
1. **Déclenchement sur 401** : Lorsqu'un code HTTP 401 est intercepté sur une requête protégée (hors `/api/v1/auth/login`), le client réseau émet le signal interne F1.3 « jeton expiré ou absent » et déclenche un appel unique à `POST /api/v1/auth/refresh` (simulée, contrat cible : auth-contrat-cible.yaml).
2. **Gestion de la concurrence** : Pendant qu'un renouvellement est en cours, toutes les requêtes protégées concurrentes attendent le même appel ; un seul appel à `/api/v1/auth/refresh` part à la fois.
3. **Rejeu transparent** : Après succès du renouvellement, le nouvel access token (15 minutes) remplace le jeton en mémoire vive volatile et la requête initiale est rejouée une seule fois. Si la requête rejouée échoue à nouveau en 401 (en-tête `X-Retry: 1`), le traitement s'arrête immédiatement sans boucle infinie.
4. **Renouvellement initial au chargement (DP-06)** : Au chargement de l'application (touche F5 ou accès initial), si aucun jeton d'accès n'est présent en mémoire vive, une tentative unique de renouvellement silencieux est engagée via `POST /api/v1/auth/refresh` avant toute réorientation vers `/login`.
5. **Éviction et redirection vers `/login`** : En cas d'échec du renouvellement (code HTTP 401 sur `/api/v1/auth/refresh` ou coupure réseau), l'access token est purgé de la mémoire vive, le cache TanStack Query est intégralement réinitialisé et l'opérateur est redirigé vers `/login` avec conservation de l'URL cible (state.from) pour réorientation post-connexion.
6. **Déconnexion explicite** : L'action de déconnexion sollicite `POST /api/v1/auth/logout` (simulée, contrat cible : auth-contrat-cible.yaml) pour ordonner au navigateur la suppression du cookie de renouvellement (`Max-Age=0`), purge la mémoire vive, détruit le cache de données et redirige vers `/login`. Conformément au modèle stateless D6, aucune révocation côté serveur n'est enregistrée.
7. **Politique d'inactivité de l'analyste** : point C4, à décider.

### 2.4 Fourniture de l'identité et de l'organisation pour la barre supérieure (Story F1.5)

Conformément à la spécification de la story F1.5 :
1. **Source des données d'affichage** : La barre supérieure permanente (`TopBar`) affiche le nom de l'organisation et le nom de l'utilisateur connecté. Ces données proviennent exclusivement de l'état de session détenu en mémoire vive volatile (`auth-memory.ts`), sans aucun stockage dans `localStorage` ni dans `sessionStorage`.
2. **Absence de route de profil utilisateur finalisée** :
   - Le contrat cible d'authentification (`docs/contrat/auth-contrat-cible.yaml`) ne prévoit pas de route de profil utilisateur (route `/api/v1/auth/me` absente du contrat cible auth E1).
   - Le schéma OpenAPI préliminaire (`docs/contrat/openapi.json`) définit une route `GET /api/v1/auth/me` dont le schéma `UserResponse` (`id`, `email`, `is_active`, `created_at`, `updated_at`) ne comporte ni nom complet de l'analyste, ni rôle opérationnel, ni rattachement d'organisation.
3. **Traitement par valeurs neutres et non-invention de données** : Le front-end s'interdit formellement de deviner ou d'inventer la moindre donnée d'identité. Lorsque la session en mémoire ne fournit pas ces éléments, l'interface affiche les valeurs neutres :
   - Utilisateur : « **Utilisateur** »
   - Organisation : « **Organisation** »
4. **Mention de statut** : **à réaligner**. Un contrat de profil enrichi (route `/api/v1/auth/me` complétée avec nom et organisation, ou route dédiée `/api/v1/users/me`) devra être formalisé côté back-end lors de l'intégration de l'Épic E1/E2.

### 2.5 Simulation de la consultation paginée et recherche des dossiers (Story F1.6)

Conformément à la spécification de la story F1.6 et au contrat cible de l'Épic E2 (`docs/contrat/openapi.json`) :
1. **Route interceptée** : `GET /api/v1/cases`
   - Statut : **simulée, contrat cible** (`openapi.json`).
   - Requiert l'en-tête `Authorization: Bearer <token>` en mémoire vive volatile.
2. **Paramètres de requête pris en charge** :
   - `limit` (entier, pagination serveur, par défaut 10, point d'architecture à décider).
   - `offset` (entier, index de début de pagination calculé côté client par `(page - 1) * limit`).
   - `search` (chaîne de caractères pour le filtrage insensible à la casse sur le titre et la description).
3. **Structure de la réponse (`CaseListResponse`)** :
   - `items` : tableau d'objets `CaseItem` (conforme au schéma cible `CaseOut` avec `id`, `organization_id`, `title`, `description`, `status`, `created_by`, `created_at`, `updated_at`, et le décompte `evidence_count`).
   - `total` / `total_items` : nombre total d'éléments correspondant au filtre de recherche.
   - `limit` : taille de page appliquée.
   - `offset` : index de départ.
   - `has_more` : booléen indiquant la présence d'une page ultérieure.
4. **Scénarios d'erreur et cas d'usage simulés** :
   - Code HTTP 401 : jeton d'accès absent ou expiré (déclenche le renouvellement silencieux F1.4 ou l'éviction vers `/login`).
   - Code HTTP 403 Forbidden : simulation via jeton `mock-forbidden-token` ou en-tête `X-Simulation-Cases: forbidden` pour tester l'état d'accès refusé.
   - Code HTTP 500 Erreur serveur : simulation via jeton `mock-server-error-token` ou en-tête `X-Simulation-Cases: server-error` pour tester la bannière d'alerte et l'action « Réessayer ».
   - Liste vide : simulation via en-tête `X-Simulation-Cases: empty` ou terme de recherche sans correspondance pour valider l'état vide (« Aucun dossier. Créez le premier. »).
5. **Règles d'architecture respectées** :
   - Aucune liste complète n'est chargée côté client : pagination stricte transmise au serveur.
   - Durée de pause de frappe (debounce) et taille de page par défaut : à décider.
   - Palette stricte appliquée sans couleur en dur dans les composants.

### 2.6 Simulation de la création d'un dossier d'investigation en modale (Story F1.7)

Conformément à la spécification de la story F1.7 et au contrat cible de l'Épic E2 (`docs/contrat/openapi.json`) :
1. **Route interceptée** : `POST /api/v1/cases`
   - Statut : **simulée, contrat cible** (`openapi.json`).
   - Requiert l'en-tête `Authorization: Bearer <token>` en mémoire vive volatile.
2. **Champs du formulaire et validation Zod** :
   - `title` : chaîne obligatoire, 1 à 255 caractères (aligné sur le schéma OpenAPI `CaseCreate`).
   - `incident_date` : chaîne obligatoire au format horodaté, pré-remplie par défaut à la date courante UTC à l'ouverture de la modale.
   - `incident_type` : sélection contrôlée. En l'absence d'énumération de typologie d'incident dans le contrat OpenAPI actuel, la valeur proposée est marquée « à décider » sans invention de données.
   - `affected_systems` : chaîne obligatoire désignant les actifs et systèmes cibles de l'incident.
   - `description` : chaîne obligatoire, 1 à 5000 caractères (aligné sur le schéma OpenAPI `CaseCreate`).
3. **Scénarios simulés par MSW** :
   - Succès (HTTP 201 Created) : retourne l'objet `CaseOut` créé, ferme la modale, invalide le cache des requêtes TanStack Query `['cases']`, réinitialise la pagination à la page 1 et affiche une notification de confirmation.
   - Rejet de validation serveur (HTTP 400 ou 422) : simulation via en-tête `X-Simulation-Create-Case: validation-error` ou corps invalide, restitution des messages d'erreur ciblés sous les champs, maintien de la modale ouverte et conservation intégrale des saisies en cours (NFR-ERR-02).
   - Accès refusé (HTTP 403 Forbidden) : simulation via `mock-forbidden-token` ou en-tête `X-Simulation-Create-Case: forbidden`, affichage de la notification « Vous n'avez pas les autorisations nécessaires pour créer un dossier dans cette organisation. », maintien de la modale ouverte et saisies conservées.
   - Erreur serveur (HTTP 500) et panne réseau : simulation via `mock-server-error-token` ou en-tête `X-Simulation-Create-Case: server-error`, notification explicite avec bouton « Réessayer », modale maintenue ouverte et saisies conservées en mémoire (NFR-ERR-02).

---

### 2.7 Simulation de la consultation et édition du contexte du dossier (Story F2.1)

Conformément à la spécification de la story F2.1 et au contrat cible de l'Épic E2 (docs/contrat/openapi.json) :
1. **Routes interceptées** :
   - GET /api/v1/cases/{case_id} : **simulée, contrat cible : openapi.json**.
   - PATCH /api/v1/cases/{case_id} : **simulée, contrat cible : à réaligner** (la méthode PATCH sur /api/v1/cases/{case_id} n'est pas encore déclarée dans le schéma OpenAPI du back-end qui ne fournit que GET).
   - Toutes deux requièrent l'en-tête Authorization: Bearer <token> en mémoire vive volatile.
2. **Champs métier et mentions d'alignement** :
   - 	itle : modifiable en ligne, validation Zod (1 à 255 caractères).
   - description : modifiable en ligne, validation Zod (max 5000 caractères), mention textuelle par défaut en teal (#019F9E) si vide (« Aucune description fournie »).
   - status : cycle de vie du dossier (open, in_progress, review, closed), affiché en lecture seule dans cette story (l'arbitrage de statut relève de F2.2).
   - created_at et updated_at (dernière activité) : horodatages UTC formatés selon la convention standard (AAAA-MM-JJ HH:mm UTC).
   - incident_date, ffected_systems et members : non présents dans le contrat OpenAPI actuel (CaseOut), affichés avec la mention textuelle « **à réaligner** » et maintenus non éditables tant que le contrat ne les prévoit pas.
3. **Scénarios simulés par MSW** :
   - Succès nominal (HTTP 200) : retourne les détails du dossier, actualise immédiatement la vue et affiche une notification de succès.
   - Dossier introuvable (HTTP 404) : simulation via case-not-found ou en-tête X-Simulation-Case: not-found, affichage d'un message neutre sans fuite de données et lien de retour vers /cases.
   - Accès refusé (HTTP 403 Forbidden) : simulation via mock-forbidden-token, case-forbidden ou en-tête X-Simulation-Case: forbidden, blocage de l'affichage des informations sensibles, affichage de la notification « Vous n'avez pas accès à ce dossier » et redirection vers /cases.
   - Erreur serveur (HTTP 500) et panne réseau : simulation via mock-server-error-token, case-500 ou en-tête X-Simulation-Case: server-error, notification explicite avec bouton « Réessayer », saisies en cours conservées en mode édition (NFR-ERR-02).

---

### 2.8 Simulation de l'évolution du statut global du dossier (Story F2.2)

Conformément à la spécification de la story F2.2 et au contrat cible de l'Épic E2 (`docs/contrat/openapi.json`) :
1. **Route interceptée** : `PATCH /api/v1/cases/{case_id}/status`
   - Statut : **simulée, contrat cible : openapi.json**.
   - Requiert l'en-tête `Authorization: Bearer <token>` en mémoire vive volatile.
2. **Matrice stricte des transitions de cycle de vie** :
   - `open` -> `in_progress`, `closed`
   - `in_progress` -> `review`, `open`, `closed`
   - `review` -> `closed`, `in_progress`
   - `closed` -> aucune transition autorisée (état terminal)
   - Toute transition absente est « à décider » et ne doit pas être proposée dans l'interface.
3. **Scénarios simulés par MSW** :
   - Succès nominal (HTTP 200) : retourne le dossier mis à jour (`CaseOut`), actualise le badge d'état en majuscules dans l'en-tête, invalide les clés TanStack Query associées et affiche une notification de succès.
   - Transition refusée par le serveur (HTTP 400 ou 409) : simulation via `X-Simulation-Status: invalid-transition` (400) ou `X-Simulation-Status: conflict` (409), affichage d'un message clair sous forme d'alerte, statut précédent restauré dans le sélecteur, saisie non perdue.
   - Accès refusé (HTTP 403 Forbidden) : simulation via `mock-forbidden-token`, `mock-viewer-token` ou `X-Simulation-Status: forbidden` pour tester le mode lecture seule ou le rejet d'habilitation.
   - Erreur serveur (HTTP 500) et panne réseau : simulation via `mock-server-error-token` ou `X-Simulation-Status: server-error`, notification explicite sans perte de saisie.

### 2.9 Simulation du téléversement de preuves avec suivi de progression (Story F3.1)

Conformément à la spécification de la story F3.1 et au contrat cible de l'Épic E3 (`docs/contrat/openapi.json`) :

1. **Route interceptée** : `POST /api/v1/cases/{case_id}/evidences`
   - Statut : **simulée, contrat cible : openapi.json**.
   - Requiert l'en-tête `Authorization: Bearer <token>` en mémoire vive volatile (Story F1.3).
   - Format de requête : `multipart/form-data` avec champ binaire obligatoire `file`.
2. **Réponse nominale** :
   - Code HTTP 202 Accepted.
   - En-tête `Location: /api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status`.
   - Corps JSON conforme au schéma `EvidenceUploadResponse` :
     ```json
     {
       "evidence_id": "00000000-0000-0000-0000-000000000001",
       "ingestion_run_id": "00000000-0000-0000-0000-000000000002"
     }
     ```
   - Bascule immédiate côté client au statut « en attente d'ingestion » affiché tel quel, sans interrogation Celery dans cette story (réservée à F3.2).
3. **Scénarios simulés par MSW** :
   - Code HTTP 401 Unauthorized : en-tête `Authorization` absent ou jeton expiré (déclenche le signal interne).
   - Code HTTP 403 Forbidden : simulation via jeton `mock-forbidden-token`, dossier `case-forbidden` ou en-tête `X-Simulation-Evidence: forbidden` pour tester l'état d'accès non autorisé.
   - Code HTTP 404 Not Found : simulation via dossier `case-not-found` ou dossier inexistant.
   - Code HTTP 413 Payload Too Large : simulation via `case-upload-413` ou en-tête `X-Simulation-Evidence: payload-too-large` pour tester le rejet serveur lié au plafond volumétrique (paramètre C3 « à caler »).
   - Code HTTP 400 Bad Request : simulation via fichier vide (0 octet) ou en-tête `X-Simulation-Evidence: empty-file`.
   - Code HTTP 500 Server Error : simulation via `case-upload-500` ou en-tête `X-Simulation-Evidence: server-error` pour tester l'état « ÉCHEC DE TRANSFERT » et le bouton « Réessayer ».

### 2.10 Simulation de l'inventaire des preuves et du suivi d'ingestion par scrutation (Story F3.2)

Conformément à la spécification de la story F3.2, à l'ADR-0008, aux conventions `12-parcours-et-etats.md` et au contrat cible de l'Épic E3 (`docs/contrat/openapi.json`) :

1. **Routes interceptées** :
   - `GET /api/v1/cases/{case_id}/evidences` : **simulée, contrat cible : openapi.json**.
   - `GET /api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status` : **simulée, contrat cible : openapi.json**.
   - Requiert l'en-tête standard `Authorization: Bearer <token>` conservé en mémoire vive volatile (Story F1.3).
2. **Cadence de scrutation et en-tête Retry-After (ADR-0008)** :
   - Pour toute preuve en cours de traitement (`pending` ou `processing`), la réponse émet l'en-tête HTTP normalisé `Retry-After: 3` (3 secondes).
   - En l'absence d'en-tête ou lors d'erreurs réseau temporaires, le front applique un recul exponentiel plafonné.
3. **Machine d'états d'ingestion (docs/frontend/12 & docs/03)** :
   - `pending` (en attente) : badge « EN ATTENTE », scrutation active.
   - `processing` (en cours) : badge « EN COURS » avec pourcentage de progression, scrutation active.
   - `completed` (terminée) : badge « INTÈGRE » avec scellement SHA-256 confirmé, arrêt de la scrutation pour cette preuve.
   - `failed` (en échec) : badge « ÉCHEC » avec motif de rejet, arrêt de la scrutation.
   - Robustesse face aux états inconnus : affichage sous la forme « État inconnu (code_brut) » sans blocage de l'interface, exclusion de l'élément pour l'analyse.
4. **Décision DP-05 (panne réseau prolongée)** :
   - Le seuil de coupure (positionné par défaut technique à 3 échecs consécutifs) reste **« à décider »** dans `docs/frontend/15-decisions-ouvertes.md` et n'est pas présenté comme une valeur acquise.
   - Le comportement d'interface demeure : arrêt de la scrutation et affichage du bandeau de rupture avec bouton « Réessayer la connexion ».
5. **Scénarios simulés par MSW** :
   - Code HTTP 401 Unauthorized : absence ou invalidité du jeton Bearer (interruption immédiate de la scrutation).
   - Code HTTP 403 Forbidden : simulation via dossier `case-forbidden`, jeton `mock-forbidden-token` ou en-tête `X-Simulation-Evidence: forbidden` (interruption immédiate du cycle de scrutation).
   - Code HTTP 500 Server Error : simulation via `case-error`, `mock-server-error-token` ou `X-Simulation-Evidence: server-error` (incrément du compteur de coupure DP-05 et bouton « Réessayer »).
   - État vide : simulation via dossier `case-empty` ou en-tête `X-Simulation-Evidence: empty` (tableau vide avec message « Aucune preuve déposée pour ce dossier » et bouton « Lancer l'analyse » désactivé).
   - Statut inconnu robuste : simulation via `evi-unknown` ou en-tête `X-Simulation-Evidence: unknown-status` (restitution de « État inconnu (unrecognized_state_code) »).

---

### 2.11 Simulation de l'inspection détaillée d'une preuve (Story F3.3)

Conformément à la spécification de la story F3.3, à l'ADR-0008, aux conventions `12-parcours-et-etats.md`, à la décision DP-04 et au contrat cible de l'épic E3 (`docs/contrat/openapi.json`) :

1. **Route interceptée** : `GET /api/v1/cases/{case_id}/evidences/{evidence_id}`
   - Statut : **simulée, contrat cible : openapi.json**.
   - Requiert l'en-tête `Authorization: Bearer <token>` conservé en mémoire vive volatile (Story F1.3).
2. **Réponse nominale (HTTP 200)** :
   - Métadonnées conformes au schéma `EvidenceRead` du contrat : `id`, `case_id`, `original_name`, `file_size`, `sha256`, `detected_type`, `imported_by`, `created_at`.
   - Champs d'enrichissement simulés pour le panneau : `ingestion_runs`, `observation_count`, `observations`, `error_message`. Ces champs ne figurent pas dans le schéma `EvidenceRead` actuel : la route est marquée **simulée, contrat cible, à réaligner** avec l'épic back-end E3.
3. **Contenu du panneau latéral** : empreinte SHA-256 intégrale en chasse fixe avec copie, nom, type détecté, taille, date d'ajout UTC, importateur, provenance (non fournie par le contrat actuel : mention neutre), historique des exécutions d'ingestion, décompte d'observations et erreurs éventuelles.
4. **Troncature DP-04** : au-delà de 500 lignes ou 64 Ko, l'aperçu de l'observation brute est tronqué et le bouton « Télécharger l'observation intégrale » permet le téléchargement direct.
5. **États gérés** : chargement par squelettes animés, erreur avec « Réessayer », accès refusé (403) avec toast et retour à la liste autorisée, introuvable (404, message neutre), état vide « Aucune observation extraite pour cette preuve », nominal.
6. **Scénarios simulés par MSW** :
   - Code HTTP 401 Unauthorized : absence ou invalidité du jeton Bearer.
   - Code HTTP 403 Forbidden : jeton `mock-forbidden-token`, dossier `case-forbidden` ou en-tête `X-Simulation-Evidence: forbidden`.
   - Code HTTP 404 Not Found : identifiant de preuve absent du dossier ou dossier `case-not-found`.
   - Code HTTP 500 Server Error : `mock-server-error-token`, `case-error`, `evi-error` ou en-tête `X-Simulation-Evidence: server-error`.
   - Troncature DP-04 : observation `obs-002` de la preuve `evi-001` (620 lignes).

---

### 2.12 Simulation de la consultation du plan proposé par le Planner (Story F4.1)

Conformément à la story F4.1, à l'ADR-0008, à la décision DP-05, aux conventions `12-parcours-et-etats.md` et au contrat cible de l'épic E5 (`docs/contrat/openapi.json`) :

1. **Routes interceptées** :
   - `GET /api/v1/cases/{case_id}/investigations` : **simulée, contrat cible : openapi.json**.
   - `GET /api/v1/cases/{case_id}/investigations/{run_id}/plan` : **simulée, contrat cible : openapi.json (à réaligner pour l'agent assigné et l'état vide)**.
   - Requièrent l'en-tête `Authorization: Bearer <token>` conservé en mémoire vive volatile (Story F1.3).
2. **Types et fidélité au contrat** : les types de réponse sont dérivés de `InvestigationPlan`, `InvestigationPlanStep` et `InvestigationRunOut` générés depuis `openapi.json`. Le schéma `InvestigationPlanStep` ne porte aucun champ d'agent assigné : l'interface affiche la mention neutre « à réaligner » plutôt qu'une valeur inventée. De même, aucun statut explicite du plan n'est prévu par le contrat : l'état « Validé » est déduit du champ contractuel `validated_plan` de la session, sans nouvelle écriture côté client.
3. **Cadence de scrutation (ADR-0008, option A)** : l'en-tête `Retry-After: 3` est émis par la simulation ; le client applique une cadence de 3 à 5 secondes, un recul exponentiel plafonné en cas d'erreur de transport, et arrête immédiatement la scrutation dès qu'un état terminal est atteint ainsi qu'au départ de la page. Aucune cadence supplémentaire n'est inventée.
4. **États simulés et affichés** : chargement par squelette animé, planification en cours (« Élaboration du plan par le Planner en cours... »), plan prêt (liste numérotée : numéro d'ordre, objectif, agent à réaligner, outil forensique, preuves visées), plan vide (« Aucun outil applicable » / « Aucun outil forensique applicable aux preuves disponibles » avec retour vers les preuves), plan validé (lecture seule avec mention « Validé »), erreur avec « Réessayer la planification », accès refusé 403 avec redirection vers `/cases`, et nominal. Un statut non répertorié est restitué sous la forme « État inconnu (code_brut) » sans blocage de la consultation.
5. **Décision DP-05 (panne réseau prolongée)** : le seuil de coupure, positionné par défaut technique, reste **« à décider »** dans `docs/frontend/15-decisions-ouvertes.md` et n'est pas présenté comme une valeur acquise. Le comportement imposé demeure : arrêt de la scrutation et affichage du bouton « Réessayer la connexion ».
6. **Lecture seule stricte** : aucun bouton de validation, de retrait ou de refus n'est présent (réservé à F4.2 / H1) ; aucun suivi d'agents (F4.3), aucun ajout d'étape et aucun écran d'audit (DP-02). Aucune écriture dans `localStorage` ni `sessionStorage` ; palette stricte (`ink`, `deep`, `teal`, `cyan`, `mist`) sans couleur en dur.
7. **Scénarios simulés par MSW** :
   - Code HTTP 401 Unauthorized : absence ou invalidité du jeton Bearer.
   - Code HTTP 403 Forbidden : jeton `mock-forbidden-token`, dossier `case-plan-forbidden` ou en-tête `X-Simulation-Plan: forbidden`.
   - Code HTTP 404 `PLAN_NOT_FOUND` : dossier `case-planning` ou en-tête `X-Simulation-Plan: planning` (premier cycle), avec `Retry-After: 3`.
   - Code HTTP 500 Server Error : `mock-server-error-token`, dossier `case-plan-error` ou en-tête `X-Simulation-Plan: server-error`.
   - Coupure de transport : en-tête `X-Simulation-Plan: network-error` (réponse réseau simulée, recul puis DP-05).
   - État vide : dossier `case-plan-empty` ou en-tête `X-Simulation-Plan: empty` (tableau `steps: []`, écart volontaire au `minItems: 1` du contrat, signalé **à réaligner** avec E5).
   - Plan validé : dossier `case-plan-validated` ou en-tête `X-Simulation-Plan: validated`.
   - Statut inconnu robuste : dossier `case-plan-unknown` ou en-tête `X-Simulation-Plan: unknown-status` (restitution de `unrecognized_state_code`).
   - Aucune session : dossier `case-plan-pending` (attente du démarrage du Planner).

### 2.13 Simulation de l'arbitrage et de la validation formelle de la porte H1 (Story F4.2)

Conformément à la story F4.2, au parcours nominal étape 5 (`docs/frontend/12`), à l'écran Plan (`docs/frontend/11`) et au contrat cible de l'épic E5 (`docs/contrat/openapi.json`) :

1. **Route interceptée** : `POST /api/v1/cases/{case_id}/investigations/{run_id}/gates/h1`
   - Statut : **simulée, contrat cible : openapi.json** (schémas `H1DecisionRequest` et `H1DecisionResponse`).
   - Requiert l'en-tête `Authorization: Bearer <token>` conservé en mémoire vive volatile (Story F1.3).
2. **Fidélité au contrat et absence d'invention** : la charge utile est strictement dérivée de `H1DecisionRequest` (`decision`, `modified_plan`, `feedback`, `return_to_planner`). La décision `modify` transmet uniquement les étapes retenues après retrait unitaire ; aucun ajout d'étape n'est proposé (hors MVP). Le motif de refus est validé côté client par un schéma Zod dont le message est en français ; la longueur maximale (2000 caractères) est celle du champ contractuel `feedback`.
3. **Confirmation obligatoire** : aucun bouton de l'écran principal n'envoie de requête. « Valider et lancer », le retrait d'une étape puis la confirmation, et « Refuser le plan » ouvrent une fenêtre de dialogue qui résume le nombre d'étapes retenues et exige une confirmation explicite. Pendant l'envoi, tous les boutons d'action sont désactivés et une seule soumission peut être en vol ; toute nouvelle tentative repasse par le dialogue via « Réessayer ».
4. **États simulés et affichés** : chargement, plan prêt avec actions actives, validation en cours, validé en lecture seule avec mention « Validé » et lien « Voir le suivi » (`/cases/:caseId/run`, F4.3), refusé avec état de replanification sans bouton de validation tant que le back n'a pas produit un nouveau plan, erreur serveur/réseau avec message et « Réessayer », accès refusé 403, nominal, et statut non répertorié restitué sous la forme « État inconnu (code_brut) ».
5. **Règles de non-validation** : sur erreur 5xx ou réseau, le plan reste « prêt » et aucune validation n'est considérée comme acquise ; la décision confirmée reste conservée en mémoire vive (NFR-ERR-02). Sur 409, l'état réel renvoyé (`status`, `current_phase`, `message`) est affiché sans validation locale, puis le plan est rafraîchi. Le scénario 409 n'étant pas déclaré dans le contrat actuel, il est marqué **à réaligner** avec l'épic E5.
6. **Scénarios simulés par MSW** :
   - Succès `approve` / `modify` (HTTP 200) : retour d'un `H1DecisionResponse`, plan scellé en lecture seule et état de session mis à jour pour les GET suivants (plan validé avec les étapes retenues).
   - Refus `reject` (HTTP 200) : `return_to_planner: true`, `feedback` obligatoire ; les GET suivants renvoient `PLAN_NOT_FOUND` avec `Retry-After: 3` jusqu'à un nouveau plan.
   - Accès refusé (HTTP 403) : jeton `mock-forbidden-token`, en-tête `X-Simulation-H1: forbidden` ou dossier `case-plan-forbidden` ; les profils `VIEWER` voient les actions masquées sans appel réseau.
   - Erreur serveur (HTTP 500) : jeton `mock-server-error-token`, en-tête `X-Simulation-H1: server-error` ou dossier `case-h1-500`.
   - Coupure de transport : en-tête `X-Simulation-H1: network-error` ou dossier `case-h1-network-error`.
   - Conflit (HTTP 409) : en-tête `X-Simulation-H1: conflict` ou dossier `case-h1-conflict`.
   - Motif vide ou décision inconnue (HTTP 422) : rejet sans mutation d'état.
7. **Périmètre exclu** : aucun suivi des agents (F4.3), aucun ajout d'étape, aucun écran d'audit (DP-02). Aucune écriture dans `localStorage` ni `sessionStorage` ; palette stricte (`ink`, `deep`, `teal`, `cyan`, `mist`) sans couleur en dur, le bouton de validation étant cyan avec texte ink.

### 2.14 Simulation de la supervision temps réel de l'orchestration (Story F4.3)

Conformément à la story F4.3, à l'ADR-0008, à DP-05, aux écrans `docs/frontend/11` et `12` et au contrat cible de l'épic E5 (`docs/contrat/openapi.json`) :

1. **Routes interceptées** :
   - `GET /api/v1/cases/{case_id}/investigations/{run_id}` : **simulée, contrat cible : openapi.json (`InvestigationRunOut`)**.
   - `POST /api/v1/cases/{case_id}/investigations/{run_id}/resume` : **simulée, contrat cible : openapi.json** (reprise, sans corps de requête).
   - La sélection de la session courante réutilise `GET /api/v1/cases/{case_id}/investigations` (F4.1). Toutes exigent l'en-tête `Authorization: Bearer` conservé en mémoire vive.
2. **Fidélité au contrat et absence d'invention** : les cartes d'agents sont dérivées des seules phases `PhaseOut` présentes dans la session. Les noms d'agents proviennent de la story ; le Corrélateur n'a aucune phase `PhaseName` correspondante et reste « à réaligner ». Aucun champ de progression, de dernier message, de diagnostic d'agent ni de journal d'événements n'existe dans le contrat : ces valeurs sont affichées « à réaligner » ou déduites des seuls horodatages contractuels (`started_at`, `completed_at`). Le statut `canceled`, demandé par la story mais absent de `InvestigationStatus`, est signalé « à réaligner ».
3. **Cadence de scrutation (ADR-0008)** : `Retry-After: 3` est renvoyé par la simulation ; le client applique 3 secondes par défaut, un recul exponentiel plafonné sur erreur de transport, et arrête la scrutation aux états terminaux (`completed`, `failed`, `canceled`) ainsi qu'au départ de la page. Aucune cadence supplémentaire n'est inventée.
4. **Commandes** : la reprise appelle la route contractuelle uniquement depuis l'état `paused`. La pause, l'annulation et la relance unitaire d'un agent n'ont aucune route dans `openapi.json` : les boutons sont présents mais désactivés ou signalés « à réaligner ». Le bouton « Annuler la session » ouvre toujours un dialogue de confirmation explicite ; aucune annulation n'est transmise sans cet accord, et aucun appel réseau n'est émis tant que le contrat ne prévoit pas la route.
5. **Échec partiel** : une phase `failed` met en évidence la carte correspondante (« ÉCHEC », icône, diagnostic à réaligner, bouton « Réessayer cet agent » désactivé) sans interrompre la scrutation ni les autres agents.
6. **États simulés et affichés** : chargement, attente, en cours, pause, échec partiel, terminé avec lien mis en avant vers `/cases/:caseId/results` (F4.5), annulé, erreur avec « Réessayer », accès refusé 403 avec redirection vers `/cases`, nominal, et statut non répertorié restitué sous la forme « État inconnu (code_brut) » avec commandes désactivées. Le journal horodaté UTC est en police mono et en lecture seule ; la mention « Initialisation du flux d'activité... » s'affiche sans événement.
7. **Décision DP-05** : après une coupure prolongée, la scrutation s'arrête et le bouton « Réessayer la connexion » est proposé. Le seuil reste « à décider » dans `docs/frontend/15-decisions-ouvertes.md`.
8. **Scénarios simulés par MSW** :
   - Nominal : dossier `case-001` ou en-tête `X-Simulation-Run: running`.
   - Attente : dossier `case-plan-pending` (aucune session) ou `case-run-pending` / en-tête `X-Simulation-Run: pending`.
   - Pause : dossier `case-run-paused` ou en-tête `X-Simulation-Run: paused` ; la reprise bascule la session simulée en `running`.
   - Échec partiel : dossier `case-run-partial` ou en-tête `X-Simulation-Run: partial-failure`.
   - Terminé : dossier `case-run-completed` ou en-tête `X-Simulation-Run: completed`.
   - Annulé : dossier `case-run-canceled` ou en-tête `X-Simulation-Run: canceled` (**à réaligner**).
   - Statut inconnu : dossier `case-run-unknown` ou en-tête `X-Simulation-Run: unknown-status` (code `unrecognized_run_code`).
   - Accès refusé (HTTP 403) : dossier `case-forbidden` / `case-run-forbidden`, jeton `mock-forbidden-token` ou en-tête `X-Simulation-Run: forbidden`.
   - Erreur serveur (HTTP 500) : dossier `case-run-error`, jeton `mock-server-error-token` ou en-tête `X-Simulation-Run: server-error`.
   - Coupure de transport : dossier `case-run-network-error` ou en-tête `X-Simulation-Run: network-error` (recul puis DP-05).
9. **Périmètre exclu** : aucune réouverture du plan ni de la porte H1 (F4.1/F4.2), aucun résultat détaillé (F4.5), aucun écran d'audit (DP-02). Aucune écriture dans `localStorage` ni `sessionStorage` ; palette stricte (`ink`, `deep`, `teal`, `cyan`, `mist`) sans couleur en dur.

---

### 2.15 Simulation de la chronologie unifiée des faits techniques (Story F4.6)

Conformément à la story F4.6, à DP-01, aux écrans `docs/frontend/11` et `12` et au contrat cible de l'épic E7 (`docs/contrat/openapi.json`) :

1. **Routes interceptées** :
   - `GET /api/v1/cases/{case_id}/observations` : **simulée, contrat cible : openapi.json**.
   - `GET /api/v1/cases/{case_id}/observations/{observation_id}` : **simulée, contrat cible : openapi.json**. Route active depuis F4.7 : le tiroir « Source » la consulte à l'ouverture, sans quitter la chronologie.
   - Requièrent l'en-tête `Authorization: Bearer` conservé en mémoire vive volatile (Story F1.3).
2. **Pagination serveur stricte (DP-01)** : `limit=100` et `offset=(page - 1) * 100` sont transmis au serveur ; un seul bloc est conservé et rendu à la fois, sans accumulation ni filtrage client sur un bloc partiel. Le bouton « Charger les 100 suivants » déclenche la tranche suivante ; `has_more` du contrat pilote sa disponibilité. Aucune autre taille de bloc n'est inventée.
3. **Filtres transmis au serveur** : `source_id`, `start_date` et `end_date` sont dérivés de la saisie UTC ; aucun filtre n'est appliqué côté client. Les filtres sont maintenus lors des changements de bloc. Les libellés de typologie (EVTX, logs, Prefetch, Registre, RAM) ne sont pas présents dans le contrat : l'identifiant de source contractuel est utilisé et le détail de typologie reste « à décider ».
4. **Fidélité au contrat et absence d'invention** : les lignes utilisent `ObservationRead` (`timestamp_utc`, `normalized_content`, `source_location`, `tool_name`, `source_id`) et `ObservationListResponse` (`items`, `total`, `total_items`, `limit`, `offset`, `has_more`). Les dates UTC sont affichées en police mono ; chaque ligne porte une date/heure UTC, un résumé court et la source technique associée sous forme de puce cliquable ouvrant le tiroir « Source » (F4.7).
5. **États simulés et affichés** : chargement par squelettes linéaires, vide (« Aucun événement chronologique. » et « Aucun événement chronologique ne correspond aux critères sélectionnés. ») avec réinitialisation des filtres, erreur serveur/réseau avec « Réessayer », accès refusé 403 avec masquage de la liste et retour aux dossiers, nominal, résultats partiels signalés par une phase `failed` du contrat, et statut inconnu restitué sous la forme « État inconnu (code_brut) » sans bloquer la consultation. F4.5 est sautée : seul l'onglet « Chronologie » est rendu.
6. **Scénarios simulés par MSW** : dossier `case-001` (nominal, plusieurs blocs complets), `case-timeline-empty` (liste vide), `case-timeline-error` (500), `case-timeline-forbidden` (403), `case-results-partial` (phase `failed`), `case-timeline-unknown` (statut non répertorié), ou en-têtes `X-Simulation-Timeline: empty|forbidden|server-error|partial-failure|unknown-status`. Le détail d'observation est simulé pour le contrat cible et appelé par le tiroir F4.7.
7. **Périmètre exclu** : aucun onglet Artefacts ou hypothèses (F4.5 sautée), aucun écran d'audit (DP-02), aucune écriture dans `localStorage` ni `sessionStorage` ; palette stricte (`ink`, `deep`, `teal`, `cyan`, `mist`) sans couleur en dur. Le panneau d'inspection de source est détaillé en 2.16 (F4.7).

---

### 2.16 Simulation du panneau latéral d'inspection de la source (Story F4.7)

Conformément à la story F4.7, à FR-RES-03, à DP-04, à C2, aux écrans `docs/frontend/11` et `12` et au contrat cible (`docs/contrat/openapi.json`) :

1. **Route interceptée** : `GET /api/v1/cases/{case_id}/observations/{observation_id}` : **simulée, contrat cible : openapi.json**. Consultation ponctuelle à l'ouverture du tiroir ; aucune scrutation (ADR-0008 ne s'applique pas ici) et aucune navigation hors de `/cases/:caseId/results`.
2. **Fidélité au contrat et absence d'invention** : la réponse est strictement `ObservationRead`. Le contrat ne porte pas de champ dédié à l'extrait brut ni à l'empreinte de preuve : la simulation les place dans `normalized_content` (champs libres), et le front affiche « à réaligner » s'ils sont absents. Le nom de fichier, l'identifiant d'événement et la ligne sont dérivés de `normalized_content` / `source_location` comme dans la chronologie F4.6. La mention exacte « Original conservé en local. Aucun contenu original transmis. » est affichée ; aucun contenu n'est journalisé ni stocké dans `localStorage` / `sessionStorage`.
3. **DP-04** : l'aperçu utilise l'utilitaire commun de troncature (500 lignes / 64 Ko). Au-delà du seuil, la bannière « Extrait tronqué à 500 lignes / 64 Ko » et le bouton « Télécharger l'extrait complet » sont affichés. Le contenu intégral n'est pas chargé pour l'affichage : seul le téléchargement direct, sur action explicite, le demande (scénario simulé `?download=full`, route définitive **à réaligner** avec E4, absente de `openapi.json`).
4. **États simulés et affichés** : chargement (squelette de métadonnées et de texte), nominal (métadonnées, extrait mono en lecture seule, empreinte tronquée avec copie), vide (« Aucun détail textuel supplémentaire pour cette observation »), erreur 404/500 (« Données de source indisponibles » avec le motif technique retourné) et « Réessayer », 403 (message d'interdiction), statut inconnu (« État inconnu (code_brut) » avec actions dépendantes désactivées). Fermeture par « Fermer » ou Échap, avec retour du focus vers la ligne d'origine.
5. **Scénarios pilotés par l'en-tête `X-Simulation-Source`** : `loading`, `empty`, `truncated` (501 lignes), `unknown-status`, `forbidden`, `error`, `not-found` ; les identifiants `case-timeline-forbidden` et `case-timeline-error` restent également applicables. Aucun onglet Artefacts/hypothèses, aucun écran d'audit (DP-02), palette stricte (`ink`, `deep`, `teal`, `cyan`, `mist`) sans couleur en dur.

---

### 2.17 Simulation de la compilation et de la prévisualisation du rapport (Story F5.1)

Conformément à la story F5.1 (FR-REP-01), à DP-03, à DP-05, à ADR-0004, à ADR-0008, aux écrans `docs/frontend/11` et `12` et à la RÈGLE CONTRAT (aucune route de rapport dans `docs/contrat/openapi.json`) :

1. **Routes interceptées** :
   - `POST /api/v1/cases/{case_id}/report/generate` : **simulée, contrat cible : ADR-0004 / ADR-0008, à réaligner avec E8**. Réponse 202 avec la tâche uniforme et l'en-tête `Retry-After: 3`. Le front ne compile rien (DP-03).
   - `GET /api/v1/cases/{case_id}/report` : **simulée, contrat cible : ADR-0004, à réaligner avec E8**. Un 404 signifie « aucun rapport finalisé » ; un 200 renvoie le document tel que reçu.
   - `GET /api/v1/cases/{case_id}/tasks/{task_id}` : **simulée, contrat cible : ADR-0008, à réaligner avec E8**. Suivi de la tâche asynchrone jusqu'à `completed` ou `failed`.
   - Toutes requièrent l'en-tête `Authorization: Bearer <token>` conservé en mémoire vive volatile (Story F1.3).
2. **Fidélité aux formats et absence d'invention** : le document simulé porte uniquement `status` (cycle de vie décrit en `12-parcours-et-etats.md`), `format` (`markdown` ou `json`, ADR-0004) et `content` (document brut). La tâche reprend strictement `task_id`, `status`, `progress` et `poll_url` (ADR-0008). Le PDF est exclu du MVP (ADR-0004). Le motif d'un échec de compilation est transmis par l'enveloppe d'erreur générique (`detail` / `error_message`) et reste **à réaligner** avec E8 : aucun champ de rapport supplémentaire n'est inventé.
3. **Cadence de scrutation (ADR-0008)** : `Retry-After: 3` est émis par la simulation ; le client applique 3 secondes par défaut, un recul exponentiel plafonné sur erreur de transport, et arrête immédiatement la scrutation aux états terminaux (`completed`, `failed`) ainsi qu'au départ de la page.
4. **Décision DP-05** : après une coupure prolongée, la scrutation s'arrête et le bouton « Réessayer la connexion » est proposé. Le seuil reste « à décider » dans `docs/frontend/15-decisions-ouvertes.md`.
5. **États simulés et affichés** : chargement, aucun rapport (bouton « Générer le rapport » actif), génération en cours (« Compilation et scellement du rapport en cours... »), rapport prêt (aperçu en huit chapitres sur fond mist avec texte ink, affiché sans modification), échec de génération avec le motif renvoyé et « Réessayer la compilation », accès refusé 403, erreur serveur/réseau avec « Réessayer », coupure DP-05, et statut non répertorié restitué sous la forme « État inconnu (code_brut) » avec actions désactivées. Un rapport sans finding validé indique « Aucun finding validé en porte H2. » sans masquer l'aperçu.
6. **Écart H2/H3** : F4.8 et F4.9 ne sont pas implémentées. Le bouton « Générer le rapport » reste actif sans contrôle H2/H3 ; l'écart est signalé dans l'interface et dans le suivi comme **à réaligner** avec la revue.
7. **Scénarios pilotés par l'en-tête `X-Simulation-Report`** : `ready`, `no-findings`, `generation-failed`, `unknown-status`, `forbidden`, `server-error`, `network-error`. Par défaut, aucun rapport n'est disponible (404). L'identifiant `case-report-forbidden` est également applicable.
8. **Périmètre exclu** : export scellé et historique des versions (F5.2), écran d'audit (DP-02), confirmation H2/H3 (F4.8/F4.9). Aucune écriture dans `localStorage` ni `sessionStorage` ; palette stricte (`ink`, `deep`, `teal`, `cyan`, `mist`) sans couleur en dur.

---

## 3. Inventaire des stories d'intégration dépendantes du contrat

Les stories front-end qui nécessitent la publication du contrat OpenAPI pour leur implémentation réelle sont classées par épic ci-dessous :

### 3.1 Épic F1 : Socle, connexion, shell du dossier et liste des dossiers
*Dépend des épics back-end E1 (Authentification) et E2 (Dossiers et rôles).*
- Story F1.1 : Formulaire de connexion et soumission des identifiants vers l'API d'authentification.
- Story F1.2 : Récupération du profil utilisateur actif et révocation de session lors de la déconnexion.
- Story F1.3 : Récupération paginée et filtrage de la liste des dossiers de l'organisation.
- Story F1.4 : Soumission du formulaire de création d'un nouveau dossier d'investigation.

### 3.2 Épic F2 : Contexte et cycle de vie du dossier
*Dépend de l'épic back-end E2 (Dossiers et isolation).*
- Story F2.1 : Consultation des métadonnées détaillées du dossier et vérification des droits d'accès.
- Story F2.2 : Mise à jour des informations administratives et techniques de l'incident.
- Story F2.3 : Modification contrôlée du statut d'état du dossier (ouvert, en cours, terminé).

### 3.3 Épic F3 : Registre et acquisition des preuves
*Dépend de l'épic back-end E3 (Preuves, téléversement, scellement SHA-256 et ingestion).*
- Story F3.1 : Téléversement en flux continu (streaming) de preuves numériques avec suivi de progression.
- Story F3.2 : Consultation de l'inventaire des preuves et suivi par scrutation du statut d'ingestion.
- Story F3.3 : Récupération des métadonnées approfondies d'une preuve et de son empreinte SHA-256 scellée.
- Story F3.4 : Contrôle de l'état d'intégrité de la chaîne de preuves et activation de l'analyse.

### 3.4 Épic F4 : Planification H1, supervision des agents, résultats et revues H2 / H3
*Dépend des épics back-end E4 (Gateway d'outils), E5 (Orchestration LangGraph et porte H1), E6 (Findings et porte H2) et E7 (Chronologie et corrélation).*
- Story F4.1 : Récupération de la proposition de plan d'investigation formulée par l'agent Planner.
- Story F4.2 : Envoi de la décision d'arbitrage de l'analyste franchissant la porte H1 (validation ou rejet motivé).
- Story F4.3 : Consultation par scrutation régulière de l'état d'avancement des agents et du flux d'activité.
- Story F4.4 : Transmission des ordres de contrôle de session (mise en pause, reprise, annulation).
- Story F4.5 : Cadre de navigation multi-vues des résultats (story sautée, hors périmètre).
- Story F4.6 : Chronologie unifiée des faits techniques avec pagination serveur par blocs de 100 (DP-01).
- Story F4.7 : Panneau latéral d'inspection de la source d'un événement forensique (simulé, contrat cible, à réaligner).
- Story F4.8 : Récupération de la synthèse pseudonymisée et enregistrement de l'autorisation explicite en porte H3.

### 3.5 Épic F5 : Restitution, rapports d'incident et clôture
*Dépend de l'épic back-end E8 (Génération de rapports et audit immuable).*
- Story F5.1 : Déclenchement de la compilation asynchrone du rapport d'enquête final.
- Story F5.2 : Récupération de l'historique des versions scellées de rapports avec empreintes de contrôle.
- Story F5.3 : Téléchargement sécurisé des archives aux formats Markdown, PDF et JSON.

---

## 4. Protocole de bascule du simulé vers le réel

Pour chaque lot fonctionnel, le remplacement de la simulation par la connectivité réelle suit une séquence stricte :

1. Réception de la notification formelle de stabilisation de l'épic back-end concerné lors du point de coordination quotidien.
2. Mise à jour de la spécification OpenAPI locale et régénération automatique des types TypeScript via openapi-typescript.
3. Vérification de l'absence de rupture de typage lors de la compilation en mode strict.
4. Désactivation du gestionnaire d'interception MSW pour les routes associées à l'épic.
5. Exécution des tests unitaires, des tests d'intégration et du scénario de bout en bout sur les données réelles fournies par l'API.
6. Enregistrement de l'épic comme « Réel » dans le tableau de suivi du présent document.

---

## 5. Tableau de bord de suivi de la synchronisation

| Lot Front-End | Épic Back-End associé | Statut du contrat d'API | Mode opérationnel actif |
|---|---|---|---|
| F1 : Socle, connexion et dossiers | E1 (Auth), E2 (Cases) | Brouillon openapi.json (routes auth en attente) | Simulation active (auth-contrat-cible.yaml) |
| F2 : Contexte du dossier | E2 (Cases) | Brouillon openapi.json (PATCH à réaligner) | Simulation active (openapi.json + à réaligner) |
| F3 : Registre des preuves | E3 (Evidence, Ingestion) | Brouillon openapi.json | Simulation active (POST, GET et GET détail openapi.json) |
| F4 : Plan, agents, résultats, revues | E4, E5, E6, E7 | Brouillon openapi.json (plan, arbitrage H1, supervision et chronologie simulés ; agent, progression, messages, journal, pause/annulation/relance, 409 H1 et panneau source à réaligner) | Simulation active pour F4.1 (GET investigations et GET plan), F4.2 (POST gates/h1), F4.3 (GET détail session et POST resume) et F4.6 (GET observations et GET détail observation) ; reste en attente pour F4.4, F4.5 (sautée) et F4.7 à F4.9 |
| F5 : Rapports et clôture | E8 (Reports), E9 (Déploiement) | Aucune route de rapport dans openapi.json (ADR-0004 / ADR-0008) | Simulation active pour F5.1 (génération et aperçu) ; F5.2 et F5.3 en attente de contrat. H2/H3 (F4.8/F4.9) à réaligner |

---

## 6. Flux complet d'authentification et gestion des sessions

Conformément à l'ADR de transport d'authentification (ADR-0011), le cycle de session entre le front-end et l'API est découpé en six phases étanches :

1. **Connexion (`/api/v1/auth/login`)** :
   L'analyste soumet ses identifiants. En cas de succès, l'API renvoie le jeton d'accès dans le corps de réponse JSON (durée de 15 minutes) et dépose un cookie httpOnly restreint au renouvellement (durée de 7 jours). Le front-end conserve l'access token exclusivement en mémoire vive (sans aucun stockage dans localStorage ni sessionStorage, et sans cookie pour les requêtes de données).
2. **Requêtes protégées** :
   Toute requête vers les endpoints protégés transmet le jeton d'accès via l'en-tête HTTP `Authorization: Bearer <jeton>`, sans cookie de données et sans nécessiter de protection anti-CSRF sur ces routes.
3. **Expiration du jeton d'accès** :
   Lorsque l'access token expire (durée de validité de 15 minutes), l'API renvoie un code HTTP 401. Le client d'interception réseau capture ce code sans interrompre l'expérience utilisateur ni afficher d'erreur prématurée.
4. **Renouvellement automatique (`/api/v1/auth/refresh`)** :
   Le client déclenche immédiatement un appel asynchrone sur la route `/api/v1/auth/refresh`. Le navigateur transmet le cookie httpOnly dédié (sans manipulation JavaScript possible et sans risque CSRF grâce à la vérification d'origine). Le serveur vérifie la validité cryptographique du refresh token (modèle stateless simple, sans rotation) et renvoie un nouvel access token de 15 minutes, chargé immédiatement en mémoire vive (sans persistance dans localStorage ni sessionStorage). La requête initialement suspendue est automatiquement rejouée.
5. **Échec du renouvellement vers `/login`** :
   Si le refresh token de 7 jours est expiré ou cryptographiquement invalide (réponse HTTP 401 sur `/api/v1/auth/refresh`), le client vide instantanément la mémoire vive (sans laisser de jeton résiduel dans localStorage ni sessionStorage) et redirige l'analyste vers `/login` avec notification d'expiration de session.
6. **Déconnexion (`/api/v1/auth/logout`)** :
   L'action de déconnexion ordonne la suppression du cookie httpOnly côté navigateur par l'API (sans révocation côté serveur, conformément aux risques acceptés du modèle stateless D6), purge l'ensemble des caches en mémoire vive (sans aucun reste dans localStorage ni sessionStorage) et renvoie l'utilisateur vers `/login`.

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-25
