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

### 2.2 Référentiel des routes protégées simulées (Stories F1.3, F1.5, F1.6, F1.7 et F2.1)

Les routes protégées ci-dessous sont interceptées et simulées par Mock Service Worker (MSW) dans `frontend/src/test/mocks/handlers.ts` pour tester l'injection de l'en-tête `Authorization: Bearer <token>`, la détection d'expiration (HTTP 401), la pagination, la recherche, la création en modale, ainsi que la consultation et l'édition du contexte :

| Méthode et route HTTP | Description opérationnelle | Mention de statut |
|---|---|---|
| `GET /api/v1/auth/me` | Profil utilisateur connecté (schéma UserResponse préliminaire sans nom ni organisation), requiert l'en-tête Authorization: Bearer en mémoire | simulée, contrat cible : openapi.json (à réaligner pour identité F1.5) |
| `GET /api/v1/cases` | Consultation paginée et recherche des dossiers (Story F1.6), avec paramètres limit, offset, search, requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json |
| `POST /api/v1/cases` | Création d'un nouveau dossier d'investigation en modale (Story F1.7), validation Zod avant envoi, champs titre, date de l'incident, type d'incident, systèmes concernés et description, requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json |
| `GET /api/v1/cases/{case_id}` | Consultation unitaire du contexte d'un dossier d'investigation (Story F2.1), requiert l'en-tête Authorization: Bearer | simulée, contrat cible : openapi.json |
| `PATCH /api/v1/cases/{case_id}` | Mise à jour en ligne du titre et de la description d'un dossier (Story F2.1), validation Zod avant envoi, requiert l'en-tête Authorization: Bearer | simulée, contrat cible : à réaligner |

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
- Story F4.5 : Récupération des observations consolidées et affichage de la chronologie UTC.
- Story F4.6 : Extraction du détail d'une observation brute pour le panneau d'inspection de la source.
- Story F4.7 : Enregistrement des décisions unitaires d'arbitrage sur les findings en porte H2.
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
| F3 : Registre des preuves | E3 (Evidence, Ingestion) | En attente | En attente de contrat / Simulation planifiée |
| F4 : Plan, agents, résultats, revues | E4, E5, E6, E7 | En attente | En attente de contrat / Simulation planifiée |
| F5 : Rapports et clôture | E8 (Reports), E9 (Déploiement) | En attente | En attente de contrat / Simulation planifiée |

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
