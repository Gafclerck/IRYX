# Architecture Technique Front-End - Plateforme IRYX (Périmètre MVP)

---

## 1. Cadre Général et Décisions Verrouillées

### 1.1 Métadonnées du Document
- **Titre** : Document d'Architecture Front-End - Plateforme IRYX (Périmètre MVP)
- **Version** : 1.0.0
- **Date** : 2026-11-25
- **Statut** : Validé par le Team Lead
- **Auteur** : Master Facilitator & System Architect (Front-End IRYX)
- **Documents sources de référence** :
  - `_bmad-output/planning-artifacts/frontend-prd.md` (PRD Front-End validé)
  - `docs/frontend/10-contexte-frontend.md` (Rôle, personas et principes d'interface)
  - `docs/frontend/11-ecrans-et-routes.md` (Cartographie des écrans, navigation et états)
  - `docs/frontend/12-parcours-et-etats.md` (Scénarios d'usage, erreurs et machines d'états)
  - `docs/frontend/13-conventions-frontend.md` (Conventions, stack technique D-27 à D-43 et charte)
  - `docs/frontend/14-contrat-et-simulation.md` (Approche Contract-First, MSW et bascule par épic)
  - `docs/adr/ADR-0011-transport-authentification.md` (Transport d'authentification et modèle sans état)
  - `docs/adr/ADR-0006-cycle-de-vie-et-expiration-jetons-jwt.md` (Cycle de vie des jetons et signature)
  - `docs/adr/ADR-0008-protocole-et-cadence-polling-http-retry-after.md` (Cadence de polling et Retry-After)
  - `docs/proposals/PROPOSITION-auth-back-E1.md` (Spécification des endpoints d'authentification)
  - `docs/frontend/tokens/iryx-design-tokens.json` (Jetons graphiques officiels de la palette stricte)

### 1.2 Principes Directeurs de Conception
1. **Le front-end reflète le back-end sans calcul métier autonome** : L'interface constitue un miroir fidèle de l'état serveur. Aucune règle de calcul forensique, déduction de statut, inférence d'état ou validation juridique ne s'exécute de façon autonome dans le navigateur.
2. **Navigation séquentielle calquée sur le canevas d'investigation** : Le parcours de traitement d'une affaire s'articule autour des cinq étapes fondamentales : Contexte, Preuves, Plan et agents, Résultats, Revue et rapport.
3. **Portes humaines inviolables (Human-in-the-Loop)** : Trois portes de contrôle bloquent visuellement et logiquement toute progression non autorisée :
   - Porte H1 : validation formelle du plan d'investigation avant l'exécution de tout outil forensique.
   - Porte H2 : arbitrage qualitatif unitaire des findings formulés par l'analyste IA.
   - Porte H3 : consentement explicite sur la synthèse pseudonymisée avant transmission externe.
4. **Thème sombre exclusif** : L'environnement graphique applique un thème sombre unique, sans déclinaison claire au MVP.
5. **Langue française unique** : L'ensemble des libellés, menus, retours système, codes d'erreur affichés et rapports est rédigé en français.
6. **Poste de travail fixe (Desktop-first)** : Résolution minimale garantie de 1280 pixels par 720 pixels, sans adaptation pour appareils mobiles ou tablettes au MVP.
7. **Suivi asynchrone par scrutation périodique (Polling REST)** : Interrogation périodique de l'API avec respect du standard HTTP 202 et de l'en-tête Retry-After, à l'exclusion formelle de WebSockets ou de Server-Sent Events (SSE).

### 1.3 Synthèse des Décisions Verrouillées (Intangibles)
Les décisions ci-dessous constituent le socle d'invariants intangibles et ne doivent faire l'objet d'aucune remise en cause :

| Domaine | Décision verrouillée | Règle impérative |
|---|---|---|
| Palette graphique | Charte stricte à cinq couleurs | Utilisation exclusive des cinq couleurs officielles : ink (`#020C0C`), deep (`#19595A`), teal (`#019F9E`), cyan (`#01DBDC`), mist (`#B7DFDF`). Tout usage de blanc pur, noir pur, rouge, vert, orange, jaune ou nuance dérivée est formellement prohibé. |
| Cadre applicatif | Décision D-27 | React (version stable courante fixée à l'initialisation du projet). |
| Moteur de build | Décision D-28 | Vite pour la rapidité de compilation et l'absence de surcharge de rendu serveur. |
| Langage | Décision D-29 | TypeScript configuré en mode strict (`strict: true`). |
| Routage | Décision D-30 | React Router en mode bibliothèque avec routes imbriquées parent-enfant. |
| Données serveur | Décision D-31 | TanStack Query pour la gestion du cache serveur, des mutations et du polling. |
| État d'interface | Décision D-32 | Hooks natifs React (useState, useReducer). Aucun magasin global métier côté client (ni Redux, ni Zustand). |
| Contrat d'API | Décision D-33 | openapi-typescript pour la génération des types et client openapi-fetch. |
| Formulaires | Décision D-34 | React Hook Form associé à Zod pour la validation déclarative des schémas. |
| Moteur de style | Décision D-35 | Tailwind CSS avec mapping direct sur les jetons de design iryx. |
| Composants UI | Décision D-36 | shadcn/ui (composants copiés basés sur les primitives accessibles de Radix UI). |
| Système d'icônes | Décision D-37 | lucide-react (accessibilité et association obligatoire avec les statuts). |
| Transferts lourds | Décision D-38 | Module d'encapsulation XMLHttpRequest pour la mesure fine de la progression. |
| Tests unitaires/composants | Décision D-39 | Vitest associé à Testing Library. |
| Tests E2E | Décision D-40 | Playwright pour la validation multi-navigateurs. |
| Qualité de code | Décision D-41 | ESLint et Prettier. |
| Déploiement | Décision D-42 | Hébergement statique d'artefacts (Vercel, Netlify ou Nginx). |
| Authentification | ADR-0011 (remplace D-43) | Jeton d'accès Bearer (15 min) en mémoire vive d'application ; refresh token en cookie httpOnly, Secure, SameSite=Strict, Path=/api/auth/refresh (7 jours) ; stateless simple sans rotation ni révocation serveur (D6). Interdiction absolue de localStorage et sessionStorage. |
| Accessibilité | Conformité WCAG 2.1 AA | Respect strict des contrastes de niveau AA (mist sur ink à 13.80, teal sur ink à 6.09, ink sur mist à 13.80). Navigation intégrale au clavier avec anneau de focus cyan (`#01DBDC`). Double signalement non chromatique (libellé majuscule + icône). Aucune exigence AAA. |
| Modalités de build | Conventions (13, section 5) | Le build du front-end ne passe jamais par bmad-build. Développement par sessions dédiées. |
| Suivi opérationnel | Conventions (13, section 5) | Suivi manuel tenu dans `frontend-sprint-status.yaml`. Interdiction absolue d'écrire dans `sprint-status.yaml` du back-end. |

---

## 2. Structure et Organisation des Dossiers

### 2.1 Arborescence Modulaire du Répertoire `frontend/`
L'arborescence du front-end isole strictement les responsabilités pour garantir une maintenabilité élevée et prévenir toute dépendance circulaire :

- `frontend/`
  - `public/` : Fichiers statiques distribués tels quels (favicon, logo vectoriel SVG conforme à la palette).
  - `e2e/` : Suites de validation de bout en bout exécutées par Playwright.
  - `src/`
    - `app/` : Initialisation de l'application, montage des fournisseurs de contexte globaux et configuration du routeur.
    - `pages/` : Composants de premier niveau associés directement à chaque route de l'application.
    - `features/` : Découpage par domaine fonctionnel regroupant composants métier, hooks TanStack Query et schémas Zod.
      - `features/auth/` : Gestion du formulaire de connexion et logique de session.
      - `features/cases/` : Liste paginée des dossiers, modale de création et tableau de bord de contexte.
      - `features/evidence/` : Dépôt et suivi d'ingestion des preuves, panneau latéral d'inspection détaillée.
      - `features/investigation/` : Revue du plan forensique (porte H1) et console d'exécution des agents.
      - `features/results/` : Chronologie unifiée, inventaire des artefacts extraits et consultation des hypothèses.
      - `features/review/` : Arbitrage qualitatif des findings (porte H2) et contrôle de pseudonymisation (porte H3).
      - `features/report/` : Prévisualisation, compilation, historique et téléchargement des rapports scellés.
    - `components/` : Composants génériques de présentation réutilisables.
      - `components/ui/` : Primitives de base issues de shadcn/ui (boutons, cartes, modales, dialogues, badges, séparateurs, tiroirs coulissants).
      - `components/layout/` : Composants structurants permanents (TopBar d'organisation, Sidebar de navigation séquentielle du dossier).
      - `components/feedback/` : Composants d'état transverses (squelettes de chargement, blocs d'erreur, états vides, bandeaux d'alerte).
    - `api/` : Couche d'infrastructure réseau et communication HTTP.
      - `api/generated/` : Types TypeScript générés automatiquement depuis le schéma OpenAPI du back-end.
      - `api/client/` : Instance configurée du client openapi-fetch avec intercepteurs de requêtes et de réponses (Bearer et gestion du 401).
      - `api/upload/` : Module de téléversement en streaming basé sur XMLHttpRequest pour le suivi de progression en pourcentage.
    - `lib/` : Fonctions utilitaires pures indépendantes de toute vue.
      - `lib/format/` : Normalisation et affichage des dates au format UTC ISO 8601, formatage des tailles d'artefacts en octets.
      - `lib/crypto/` : Utilitaires de présentation et de troncature sécurisée des empreintes SHA-256.
      - `lib/validation/` : Primitives partagées pour les schémas Zod.
    - `styles/` : Feuilles de styles globales et configuration des jetons Tailwind.
    - `test/` : Infrastructure de test unitaire et d'intégration.
      - `test/mocks/` : Gestionnaires d'interception et fixtures de données pour Mock Service Worker (MSW).
      - `test/setup/` : Configuration globale de l'environnement de test Vitest et Testing Library.

### 2.2 Rôle et Responsabilités de Chaque Dossier

| Répertoire | Responsabilité principale | Règles d'exclusion |
|---|---|---|
| `src/app/` | Instanciation du client TanStack Query, mise en place des gestionnaires d'erreurs globaux et montage de l'arborescence React Router. | Ne contient aucune règle métier ni composant d'affichage spécifique à un écran. |
| `src/pages/` | Assemblage des composants de vue pour une route donnée. Fait le lien entre les paramètres d'URL (ex. `:caseId`) et les fonctionnalités correspondantes. | Ne contient pas de logique d'appel API directe ni de formulaire complexe (délégués aux features). |
| `src/features/` | Cœur fonctionnel de l'application découpé par domaine métier. Contient les formulaires spécifiques, les hooks TanStack Query dédiés et les schémas de validation Zod associés. | Ne doit jamais importer un élément provenant du répertoire `pages/`. |
| `src/components/ui/` | Bibliothèque de composants d'interface pure (boutons, champs, onglets) conformes à l'accessibilité Radix UI et stylisés via Tailwind avec la palette stricte. | Ne contient aucun hook d'appel réseau ni référence directe au modèle métier. |
| `src/components/layout/` | Matérialise le cadre permanent de l'application (TopBar transverse, Sidebar de dossier à cinq étapes). | Ne gère pas de données métier en dehors du contexte d'en-tête (dossier actif, utilisateur). |
| `src/components/feedback/` | Garantit la restitution homogène des cinq états obligatoires (chargement, vide, erreur, accès refusé, nominal). | Composants strictement visuels et réutilisables. |
| `src/api/` | Encapsulation de tous les transferts HTTP. Comprend le client d'interception d'authentification, les types dérivés du contrat OpenAPI et le module d'envoi lourd XMLHttpRequest. | Ne contient aucun composant React ni élément de rendu visuel. |
| `src/lib/` | Fonctions de calcul pur (troncature SHA-256, conversion de dates UTC). | Totalement agnostique de React et de l'interface graphique. |
| `src/styles/` | Définition des classes Tailwind basées exclusivement sur les cinq couleurs autorisées. | Interdiction formelle de toute classe ou valeur chromatique hors palette. |
| `src/test/` | Fournit les mocks MSW reproduisant fidèlement les réponses de l'API pour les tests et la simulation. | Aucun code de production ne doit dépendre de ce répertoire. |
| `e2e/` | Scénarios de tests de bout en bout automatisés avec Playwright. | Exécuté hors du cycle de build Vite standard. |

### 2.3 Matrice et Règles de Dépendances Directionnelles
Pour interdire les dépendances circulaires et préserver le découplage, les flux d'importation entre répertoires sont strictement réglementés :

| Source de l'import | Répertoires cibles autorisés en import | Répertoires cibles formellement interdits |
|---|---|---|
| `src/pages/` | `features/`, `components/`, `api/`, `lib/` | Aucun |
| `src/features/` | `features/` (modules frères autorisés avec parcimonie), `components/`, `api/`, `lib/` | `pages/`, `app/` |
| `src/components/` | `components/ui/`, `components/feedback/`, `lib/` | `pages/`, `features/`, `api/`, `app/` |
| `src/api/` | `lib/` | `pages/`, `features/`, `components/`, `app/` |
| `src/lib/` | Fonctions utilitaires internes à `lib/` | `pages/`, `features/`, `components/`, `api/`, `app/` |

---

## 3. Architecture de Routage et Navigation

### 3.1 Cartographie Complète des Routes Applicatives
L'application s'articule autour d'une hiérarchie de routes parent-enfant gérée par React Router (décision D-30) :

| Chemin de la route | Désignation de l'écran | Étape du canevas | Layout associé | Statut d'accès |
|---|---|---|---|---|
| `/login` | Formulaire de connexion | Hors canevas | Page publique sans layout | Public non authentifié |
| `/cases` | Liste des dossiers et création | Hors canevas | Shell général avec TopBar | Authentifié |
| `/cases/:caseId` | Contexte et tableau de bord | Étape 1 : Contexte | Shell du dossier (TopBar + Sidebar) | Membre du dossier |
| `/cases/:caseId/evidence` | Registre et téléversement des preuves | Étape 2 : Preuves | Shell du dossier (TopBar + Sidebar) | Membre du dossier |
| `/cases/:caseId/evidence/:evidenceId` | Panneau de détail d'une preuve | Étape 2 : Preuves | Shell du dossier avec tiroir coulissant | Membre du dossier |
| `/cases/:caseId/plan` | Revue du plan et arbitrage H1 | Étape 3 : Plan et agents | Shell du dossier (TopBar + Sidebar) | Membre (arbitrage analyste) |
| `/cases/:caseId/run` | Console d'exécution des agents | Étape 3 : Plan et agents | Shell du dossier (TopBar + Sidebar) | Membre du dossier |
| `/cases/:caseId/results` | Exploration des résultats (3 onglets) | Étape 4 : Résultats | Shell du dossier (TopBar + Sidebar) | Membre du dossier |
| `/cases/:caseId/review` | Revue H2 des findings et porte H3 | Étape 5 : Revue et rapport | Shell du dossier (TopBar + Sidebar) | Analyste habilité |
| `/cases/:caseId/report` | Compilation et téléchargement rapport | Étape 5 : Revue et rapport | Shell du dossier (TopBar + Sidebar) | Membre du dossier |

### 3.2 Imbrication des Routes et Shell du Dossier
Le routage exploite le patron des routes imbriquées (Nested Routes) pour factoriser la présentation et éviter les recalculs d'affichage superflus :

1. **Layout racine authentifié (`AuthenticatedLayout`)** :
   - Enveloppe toutes les routes protégées.
   - Intègre la TopBar transverse permanente : logo IRYX, nom de l'organisation active, identifiant et rôle de l'utilisateur connecté, commande de déconnexion.
2. **Layout du dossier (`CaseShellLayout`)** :
   - Route parent : `/cases/:caseId`.
   - Charge les métadonnées de base du dossier pour initialiser le contexte.
   - Affiche à gauche la barre latérale (Sidebar) matérialisant en permanence les cinq étapes du canevas d'investigation :
     - Étape 1 : Contexte (`/cases/:caseId`)
     - Étape 2 : Preuves (`/cases/:caseId/evidence`)
     - Étape 3 : Plan et agents (`/cases/:caseId/plan` et `/cases/:caseId/run`)
     - Étape 4 : Résultats (`/cases/:caseId/results`)
     - Étape 5 : Revue et rapport (`/cases/:caseId/review` et `/cases/:caseId/report`)
   - Chaque entrée de la Sidebar reflète son statut dynamique : non démarrée, en cours, terminée, ou bloquée par une porte humaine.
   - Les routes enfants s'affichent dynamiquement dans la zone centrale de contenu (`Outlet`).
3. **Synchronisation du panneau latéral de détail de preuve** :
   - La route `/cases/:caseId/evidence/:evidenceId` est une route enfant directe affichant la vue de liste des preuves en arrière-plan tout en ouvrant le panneau latéral coulissant d'inspection détaillée.
   - La fermeture du panneau latéral déclenche une navigation vers `/cases/:caseId/evidence`, garantissant que l'état d'ouverture ou de fermeture du panneau est strictement synchronisé avec l'URL du navigateur (URL partageable).

### 3.3 Mécanisme du Garde d'Authentification (`AuthGuard`)
L'accès aux routes protégées est subordonné au passage dans le composant garde `AuthGuard` :
- Le garde interroge l'état de session détenu en mémoire vive applicative.
- Si un jeton d'accès Bearer valide est présent en mémoire : l'accès à la route demandée est accordé immédiatement.
- Si le jeton d'accès est absent (par exemple lors d'un rafraîchissement complet de la page par la touche F5 du navigateur) :
  - Le garde déclenche une tentative initiale et silencieuse de renouvellement en appelant l'endpoint `/api/auth/refresh`.
  - Le navigateur transmet automatiquement le cookie httpOnly de renouvellement.
  - Si le renouvellement aboutit : le nouvel access token est enregistré en mémoire vive et l'accès à la route demandée est accordé sans interruption.
  - Si le renouvellement échoue (cookie absent, expiré ou invalide) : le garde interrompt la navigation et redirige immédiatement vers `/login`. L'URL initialement demandée est transmise dans l'état de navigation pour permettre une réorientation automatique dès la connexion réussie.

### 3.4 Gestion des Redirections sur Codes HTTP 401 et 403
Une distinction architecturale rigoureuse sépare le traitement des erreurs d'authentification et d'autorisation :

| Code HTTP renvoyé | Cause métier | Comportement architectural du front-end |
|---|---|---|
| HTTP 401 Unauthorized | Jeton d'accès Bearer expiré (après 15 min) ou signature invalide. | Interception transparente par le client réseau. Suspension des requêtes sortantes et appel de `/api/auth/refresh`. En cas d'échec du renouvellement (expiration du refresh token de 7 jours), purge de la mémoire vive et redirection vers `/login` avec la notification « Session expirée. Veuillez vous reconnecter. » |
| HTTP 403 Forbidden | L'utilisateur authentifié n'appartient pas à l'organisation ou n'est pas membre habilité sur le dossier cible. | Interception par le composant de vue. Blocage de l'affichage des données confidentielles, notification toast explicite « Vous n'avez pas accès à ce dossier » et redirection automatique vers `/cases`. |

---

## 4. Gestion des Données Serveur et de l'État Applicatif

### 4.1 Modèle d'État sans Magasin Global Métier Côté Client
Conformément aux décisions D-31 et D-32 :
- **État serveur** : Pris en charge intégralement par TanStack Query. L'application ne conserve aucune copie persistante ou dupliquée des dossiers, preuves, étapes de plan, agents, résultats ou rapports dans un magasin global de type Redux ou Zustand.
- **État d'interface local** : Géré via les hooks natifs React (`useState`, `useReducer`, `useContext`). Cet état est restreint aux besoins éphémères de présentation : saisie en cours dans un champ, filtre temporel appliqué sur la chronologie, visibilité d'un panneau latéral ou sélection d'onglet.
- **Résilience des saisies** : En cas d'incident réseau temporaire, les formulaires non validés conservent leurs données dans l'état local du composant sans écriture dans le stockage du navigateur.

### 4.2 Hiérarchie des Clés de Requêtes (Query Keys) et Politiques de Cache
TanStack Query structure le cache mémoire à travers des clés hiérarchiques prédictibles, facilitant les invalidations ciblées :

| Clé de requête TanStack Query | Entité métier associée | Durée de fraîcheur (`staleTime`) | Durée en cache (`gcTime`) |
|---|---|---|---|
| `['cases', { page, search }]` | Liste paginée et filtrée des dossiers | 30 secondes | 5 minutes |
| `['cases', caseId]` | Contexte et métadonnées d'un dossier | 60 secondes | 10 minutes |
| `['cases', caseId, 'evidence']` | Registre des preuves du dossier | 10 secondes | 5 minutes |
| `['cases', caseId, 'evidence', evidenceId]` | Métadonnées détaillées d'une preuve | 30 secondes | 5 minutes |
| `['cases', caseId, 'plan']` | Plan d'investigation et statut porte H1 | 5 secondes | 5 minutes |
| `['cases', caseId, 'run']` | Session d'exécution des agents et journal | 0 seconde (temps réel) | 5 minutes |
| `['cases', caseId, 'results', { tab, filters }]` | Observations, chronologie et hypothèses | 30 secondes | 10 minutes |
| `['cases', caseId, 'review']` | Findings H2 et prévisualisation H3 | 10 secondes | 5 minutes |
| `['cases', caseId, 'report']` | Rapports compilés et historique scellé | 60 secondes | 15 minutes |

### 4.3 Protocole de Scrutation Asynchrone (Polling REST - ADR-0008)
Les opérations lourdes exécutées par le back-end (tâches Celery d'ingestion de preuves, exécution des agents LangGraph, compilation de rapport) renvoient une réponse HTTP 202 Accepted. Le front-end implémente le protocole suivant :

1. **Cadence de scrutation définie par ADR-0008** :
   - Le serveur positionne l'en-tête standard `Retry-After: 3` (3 secondes) sur chaque réponse HTTP 202.
   - Le hook TanStack Query configure le paramètre `refetchInterval` sur la valeur indiquée par le serveur (défaut : 3 secondes ; tolérance nominale comprise entre 3 et 5 secondes).
2. **Recul exponentiel (Exponential Backoff)** :
   - En cas d'erreur de transport réseau lors d'un appel de scrutation, le client n'interrompt pas brutalement la surveillance : il applique un recul temporisé progressif (ex. 3s, puis 6s, 12s, plafonné) pour éviter d'engorger le serveur tout en maintenant la résilience.
3. **Conditions d'arrêt impératives de la scrutation** :
   - La scrutation est conditionnée par l'indicateur d'état retourné dans le corps de réponse.
   - Elle s'interrompt immédiatement dès que la tâche atteint un statut terminal :
     - Pour l'ingestion : arrêt dès que le statut passe à `completed` ou `failed`.
     - Pour l'investigation : arrêt dès que le statut de session passe à `completed` ou `failed`.
     - Pour la compilation de rapport : arrêt dès que le statut passe à `validated` ou `failed`.
   - La scrutation est également suspendue sans délai lorsque l'analyste quitte l'écran concerné (démontage du composant React).

### 4.4 Politique d'Invalidation du Cache après Mutation
Pour garantir l'intégrité de l'affichage sans rechargement de page, chaque opération de mutation déclenche l'invalidation ciblée des requêtes associées :

| Action utilisateur (Mutation) | Endpoint API sollicité | Clés de requêtes invalidées après succès |
|---|---|---|
| Création d'un nouveau dossier | `POST /api/cases` | `['cases']` |
| Mise à jour du statut d'un dossier | `PATCH /api/cases/:caseId` | `['cases', caseId]`, `['cases']` |
| Téléversement d'une nouvelle preuve | `POST /api/cases/:caseId/evidence` | `['cases', caseId, 'evidence']` |
| Validation formelle du plan (Porte H1) | `POST /api/cases/:caseId/plan/validate` | `['cases', caseId, 'plan']`, `['cases', caseId, 'run']` |
| Rejet motivé du plan d'investigation | `POST /api/cases/:caseId/plan/reject` | `['cases', caseId, 'plan']` |
| Ordre de contrôle d'agent (pause, reprise) | `POST /api/cases/:caseId/run/control` | `['cases', caseId, 'run']` |
| Relance sélective d'un agent en échec | `POST /api/cases/:caseId/run/retry-agent` | `['cases', caseId, 'run']` |
| Décision sur un finding (Porte H2) | `POST /api/cases/:caseId/findings/:id/decide` | `['cases', caseId, 'review']`, `['cases', caseId, 'results']` |
| Approbation de transmission externe (H3) | `POST /api/cases/:caseId/review/authorize-h3` | `['cases', caseId, 'review']` |
| Déclenchement compilation rapport | `POST /api/cases/:caseId/report/generate` | `['cases', caseId, 'report']` |

---

## 5. Architecture de Sécurité et Cycle de Vie de l'Authentification (ADR-0011)

### 5.1 Ségrégation des Jetons et Interdiction Absolue des Stockages Persistants
Conformément à l'ADR-0011 et aux décisions D1, D3, D6 et D-43 révisée :

1. **Jeton d'accès (Access Token Bearer)** :
   - Durée de vie strictement bornée à **15 minutes**.
   - Conservé **exclusivement en mémoire vive volatile de l'application cliente** (variable encapsulée au sein de la couche d'infrastructure réseau `src/api/client/`).
   - **Règle absolue d'interdiction** : Il est formellement interdit de stocker le jeton d'accès, sous quelque forme que ce soit, dans `localStorage` ou dans `sessionStorage`. Aucun jeton d'accès n'est écrit dans les stockages du navigateur.
2. **Jeton de renouvellement (Refresh Token)** :
   - Durée de vie fixée à **7 jours**.
   - Délivré par le serveur sous forme de cookie HTTP doté des attributs de sécurité maximaux :
     - `HttpOnly` : Empêche toute lecture, manipulation ou extraction par les scripts JavaScript (étanchéité absolue contre les attaques XSS).
     - `Secure` : Imposé pour le chiffrement des échanges en HTTPS.
     - `SameSite=Strict` : Bloque tout envoi du cookie lors d'une navigation transverse ou d'une requête externe (protection anti-CSRF native).
     - `Path=/api/auth/refresh` : Restreint l'exposition et la transmission du cookie au seul endpoint de renouvellement.
3. **Modèle sans état simple (Stateless D6)** :
   - Le refresh token est signé cryptographiquement par le serveur mais ne fait l'objet d'aucun enregistrement dans une table de base de données.
   - Aucune rotation unitaire n'est effectuée lors du renouvellement : le même cookie de 7 jours reste valide jusqu'à son terme.
   - Les risques associés (validité continue pendant 7 jours, absence de détection de rejeu et déconnexion locale sans révocation serveur) sont formellement acceptés par la gouvernance du projet.

### 5.2 Interception Réseau et Transmission Sécurisée
Toute requête émise vers les endpoints protégés de l'API transite par le client réseau configuré :
- Le client extrait le jeton d'accès actif présent en mémoire vive.
- Il injecte l'en-tête HTTP standard : `Authorization: Bearer <jeton_acces>`.
- Les requêtes de données métier ne transmettent aucun cookie d'authentification, ce qui élimine par construction tout risque d'attaque CSRF sur l'ensemble des opérations d'enquête.

### 5.3 Mécanisme d'Expiration (401), File d'Attente et Renouvellement Silencieux
Le processus de renouvellement continu garantit la persistance de la session de travail de l'analyste sans interruption visuelle :

1. **Détection du code HTTP 401** : Lorsqu'un appel de données renvoie une réponse 401 consécutive à l'expiration des 15 minutes du jeton d'accès, l'intercepteur réseau intercepte la réponse avant sa transmission aux composants React.
2. **Gestion de la concurrence via file d'attente (Request Queue)** :
   - Si plusieurs requêtes réseau sont émises simultanément lors de l'expiration du jeton, une seule requête de renouvellement est déclenchée vers `/api/auth/refresh`.
   - L'ensemble des requêtes concurrentes en attente est placé dans une file d'attente en mémoire vive, évitant les appels multiples redondants.
3. **Appel de renouvellement (`POST /api/auth/refresh`)** :
   - Le navigateur transmet automatiquement le cookie httpOnly de renouvellement.
   - Le serveur back-end valide la concordance de l'en-tête d'origine (`Origin` ou `Sec-Fetch-Site`) pour se prémunir contre toute sollicitation cross-site non sollicitée.
   - Le serveur renvoie un nouvel access token d'une validité de 15 minutes.
4. **Réarmement et rejeu transparent** :
   - Le nouvel access token est rechargé immédiatement dans la mémoire vive volatile de l'application (toujours sans aucun recours à `localStorage` ni `sessionStorage`).
   - L'ensemble des requêtes suspendues dans la file d'attente est dépilé et réexécuté avec le nouveau jeton Bearer.
   - L'utilisateur ne perçoit aucune déconnexion ni saut d'affichage.

### 5.4 Échec de Renouvellement et Éviction Sécurisée
Si la requête de renouvellement sur `/api/auth/refresh` échoue (réponse HTTP 401 consécutive à l'expiration des 7 jours du cookie ou à une signature cryptographique invalide) :
- Le client réseau purge immédiatement le jeton d'accès de la mémoire vive (sans laisser de traces résiduelles dans `localStorage` ni `sessionStorage`, qui demeurent vierges de tout jeton).
- Toutes les requêtes en attente dans la file sont rejetées avec une erreur d'authentification.
- Le cache de données TanStack Query est intégralement réinitialisé.
- L'utilisateur est redirigé immédiatement vers la route `/login` avec la notification descriptive : « Session expirée. Veuillez vous reconnecter. »
- L'URL de la page sur laquelle l'analyste se trouvait est mémorisée dans l'état de navigation pour permettre un retour transparent après ré-authentification.

### 5.5 Déconnexion Explicite (Logout)
Lorsque l'analyste actionne la commande « Se déconnecter » dans la TopBar :
1. Le front-end émet une requête asynchrone `POST /api/auth/logout`.
2. Le serveur back-end répond en envoyant un en-tête `Set-Cookie` réinitialisant le cookie de renouvellement avec une date d'expiration passée (`Max-Age=0`), ce qui ordonne sa suppression immédiate par le navigateur.
3. Conformément au modèle sans état simple (D6), aucune écriture en base ni inscription dans une liste de révocation n'est exécutée côté serveur.
4. Côté front-end, l'application vide intégralement la variable d'access token en mémoire vive (rappel : aucun stockage n'a jamais été effectué dans `localStorage` ni dans `sessionStorage`).
5. Le cache TanStack Query est détruit et l'analyste est immédiatement redirigé vers l'écran `/login`.

### 5.6 Protection Contre les Vulnérabilités Web Majeures

| Menace de sécurité | Vecteur d'attaque | Mesure de protection architecturale appliquée |
|---|---|---|
| Attaque XSS (Cross-Site Scripting) | Injection de script malveillant pour subtiliser des jetons de session. | Le jeton d'accès est exclusivement en mémoire vive et jamais dans `localStorage` ni `sessionStorage`. Le refresh token est protégé par l'attribut `httpOnly`, le rendant physiquement inaccessible aux scripts. Les composants React échappent nativement les contenus et une politique CSP stricte interdit les scripts en ligne. |
| Attaque CSRF (Cross-Site Request Forgery) | Falsification de requêtes via des cookies automatiques. | Toutes les requêtes d'API de données s'appuient exclusivement sur l'en-tête `Authorization: Bearer`, insensible aux envois automatiques de cookies. Sur l'unique route sous cookie (`/api/auth/refresh`), la combinaison de `SameSite=Strict` et du contrôle de l'en-tête `Origin` côté serveur bloque toute attaque transverse. |
| Vol d'écran ou session abandonnée | Accès physique ou reprise de session après départ de l'analyste. | Jeton d'accès de courte durée (15 minutes). Purge complète de la mémoire d'application à la fermeture de l'onglet ou à la déconnexion explicite. |

---

## 6. Découplage, Simulation (MSW) et Protocole de Bascule par Épic

### 6.1 Approche Contrat d'Abord (Contract-First) et Génération de Typage
Conformément au document `docs/frontend/14-contrat-et-simulation.md` :
- Le schéma OpenAPI publié par la piste back-end constitue la **source unique de vérité** définissant l'ensemble des modèles de données, des paramètres de requêtes et des structures de réponses.
- Le front-end s'interdit formellement de maintenir des types TypeScript manuels pour les entités de l'API.
- L'outil `openapi-typescript` génère automatiquement les définitions de types TypeScript dans le répertoire `src/api/generated/schema.ts`.
- Le client d'appel réseau `openapi-fetch` consomme ces types pour garantir une vérification stricte à la compilation : toute discordance entre le modèle attendu et l'implémentation du composant provoque une erreur de build immédiate.

### 6.2 Couche de Simulation Déterministe (Mock Service Worker - MSW)
Pour permettre la conception, le développement ergonomique et la validation des parcours d'interface avant la livraison effective des endpoints du back-end :
- Une couche d'interception réseau Mock Service Worker (MSW) est intégrée dans `src/test/mocks/`.
- Les gestionnaires d'interception (handlers) interceptent les appels HTTP au niveau du navigateur (Service Worker en développement) et de Node.js (lors des tests unitaires et composants Vitest).
- Les jeux de données simulés (fixtures) respectent fidèlement la structure des schémas OpenAPI et reproduisent l'ensemble des cas nominaux et des cas d'erreur (ex. échec d'ingestion, preuve non intègre, indisponibilité de modèle externe).

### 6.3 Découpage des Épics Front-End et Dépendances Back-End
Le développement front-end est ordonnancé en cinq épics (F1 à F5) synchronisés avec les livrables du back-end :

| Lot Front-End | Périmètre fonctionnel couvert | Épics Back-End associés | Statut actuel du contrat d'API |
|---|---|---|---|
| Épic F1 | Socle technique, authentification, layout permanent et liste paginée des dossiers | E1 (Authentification JWT), E2 (Organisations et dossiers) | En attente de contrat / Simulation planifiée |
| Épic F2 | Contexte du dossier et gestion du cycle de vie | E2 (Dossiers et isolation) | En attente de contrat / Simulation planifiée |
| Épic F3 | Registre des preuves, téléversement lourd et suivi d'ingestion SHA-256 | E3 (Preuves, scellement et Celery) | En attente de contrat / Simulation planifiée |
| Épic F4 | Planification H1, supervision des agents, résultats et revues H2 / H3 | E4 (Gateway outils), E5 (LangGraph / H1), E6 (Findings / H2), E7 (Chronologie) | En attente de contrat / Simulation planifiée |
| Épic F5 | Compilation du rapport scellé, historique et téléchargements | E8 (Rapports et audit immuable), E9 (Déploiement) | En attente de contrat / Simulation planifiée |

### 6.4 Protocole de Bascule du Simulé vers le Réel par Épic
Pour chaque épic front-end, le passage de la simulation MSW à la connectivité avec l'API réelle s'effectue selon une procédure rigoureuse en six étapes :

1. **Notification de disponibilité** : Réception de la confirmation officielle de stabilisation de l'épic back-end correspondant.
2. **Actualisation du contrat OpenAPI** : Récupération du schéma OpenAPI stabilisé et exécution de la commande de régénération des types TypeScript (`openapi-typescript`).
3. **Contrôle de typage strict** : Exécution de la vérification TypeScript (`tsc --noEmit`) pour valider l'absence de rupture de contrat.
4. **Désactivation sélective des mocks MSW** : Désactivation des intercepteurs MSW pour les seules routes associées à l'épic concerné, les autres routes restant sous simulation.
5. **Validation des tests sur API réelle** : Exécution de la suite de tests unitaires, de tests de composants et du scénario de bout en bout Playwright contre l'environnement de test du back-end.
6. **Mise à jour du statut** : Inscription du statut « Réel » pour l'épic dans le document de suivi.

---

## 7. Stratégie de Test et Assurance Qualité

### 7.1 Pyramide de Tests et Outillage Technique

| Niveau de test | Outil retenu | Cible principale de validation | Fréquence d'exécution |
|---|---|---|---|
| Tests unitaires | Vitest | Fonctions utilitaires pures de `src/lib/`, validateurs Zod, intercepteur d'authentification et gestionnaire de file d'attente sur 401. | À chaque commit et avant toute intégration. |
| Tests de composants | Vitest + Testing Library | Composants d'interface, formulaires React Hook Form, gestion des cinq états obligatoires et accessibilité. | À chaque build local et en intégration continue. |
| Tests de bout en bout | Playwright | Parcours complet de démonstration nominale sur station Chromium, Firefox et WebKit. | Validation de fin d'épic et jalons de recette. |

### 7.2 Couverture des Tests Unitaires
Les tests unitaires valident le déterminisme des modules isolés sans rendu graphique :
- **Utilitaires cryptographiques et de formatage (`src/lib/`)** : Troncature exacte des empreintes SHA-256 sans altération des caractères significatifs, formatage des dates en UTC ISO 8601, conversion des tailles d'artefacts.
- **Schémas de validation Zod (`src/features/*/schemas/`)** : Rejet des identifiants vides ou malformés sur la connexion, validation des champs obligatoires du formulaire de création de dossier, contrôle de la présence d'un motif obligatoire lors du rejet d'un plan H1 ou d'un finding H2.
- **Intercepteur d'authentification et gestion de session (`src/api/client/`)** : Vérification du stockage de l'access token en mémoire vive uniquement (vérification de l'absence totale de données dans `localStorage` et `sessionStorage`), interception du 401, mécanisme de mise en file d'attente des requêtes concurrentes, réémission des requêtes après renouvellement.

### 7.3 Couverture des Tests de Composants et Accessibilité
Les tests de composants s'assurent de la fidélité de restitution et du respect des exigences non fonctionnelles :
1. **Validation systématique des cinq états obligatoires** : Chaque vue d'écran est testée pour garantir la prise en charge sans régression de :
   - L'état de chargement (affichage de squelettes de substitution animés).
   - L'état vide (message descriptif explicite avec invitation à l'action).
   - L'état d'erreur technique (message d'erreur compréhensible avec bouton de réessai).
   - L'état d'accès refusé (redirection ou message de blocage de sécurité).
   - L'état nominal (affichage interactif complet des données métier).
2. **Contrôle d'accessibilité WCAG 2.1 AA** :
   - Navigation intégrale au clavier sans blocage de focus (séquence Tabulation, validation par Entrée ou Espace).
   - Présence systématique de l'anneau de focus visuel cyan (`#01DBDC`) de 2 pixels de contour sur tout élément interactif.
   - Vérification du principe de signalement non chromatique : chaque badge de statut ou de sévérité doit comporter simultanément une icône lucide-react et un libellé textuel en lettres majuscules (ex. « ÉLEVÉE », « MOYENNE », « FAIBLE », « VALIDÉ », « ÉCHEC »).

### 7.4 Parcours Nominal de Bout en Bout (E2E) - Scénario de Référence
Un parcours automatisé unique instrumenté sous Playwright (décision D-40) valide l'enchaînement complet des dix étapes du scénario de démonstration opérationnelle :

| Étape E2E | Action simulée | Critère de succès vérifié |
|---|---|---|
| Étape 1 | Saisie des identifiants sur `/login` et soumission. | Redirection réussie vers `/cases`, jeton d'accès présent en mémoire vive, aucun jeton dans `localStorage` ni `sessionStorage`. |
| Étape 2 | Ouverture de la modale « Nouveau dossier », saisie des métadonnées et validation. | Création enregistrée et navigation immédiate vers `/cases/:caseId`. |
| Étape 3 | Navigation vers `/cases/:caseId/evidence`, dépôt glisser-déposer de deux fichiers de preuves. | Affichage des jauges de progression individuelles via XMLHttpRequest, puis affichage des statuts d'ingestion. |
| Étape 4 | Surveillance par scrutation du scellement SHA-256. | Atteinte du statut intègre (`completed`) et activation du bouton « Lancer l'analyse ». |
| Étape 5 | Clic sur « Lancer l'analyse » et orientation vers `/cases/:caseId/plan`. | Affichage de la séquence d'outils de l'agent Planner ; validation formelle du plan franchissant la porte H1. |
| Étape 6 | Orientation automatique vers la console d'exécution `/cases/:caseId/run`. | Scrutation de l'activité des cartes d'agents jusqu'à l'état terminé (`completed`) ; bouton « Voir les résultats » actif. |
| Étape 7 | Navigation vers `/cases/:caseId/results`. | Consultation de la chronologie unifiée des faits techniques ; clic sur un événement pour vérifier l'ouverture du panneau latéral d'inspection de la source. |
| Étape 8 | Navigation vers `/cases/:caseId/review`. | Validation formelle de deux findings et rejet motivé d'une hypothèse en porte H2. |
| Étape 9 | Consultation de la synthèse pseudonymisée en porte H3. | Refus de la transmission externe et sélection de l'option « Générer le rapport en local ». |
| Étape 10 | Navigation vers `/cases/:caseId/report`. | Déclenchement de la compilation, prévisualisation du document complet et déclenchement du téléchargement de l'archive scellée. |

---

## 8. Matrice de Cohérence et Traçabilité avec le PRD

### 8.1 Matrice des Exigences Fonctionnelles (FR)
Le tableau ci-dessous établit la correspondance exhaustive entre chaque exigence fonctionnelle définie dans `_bmad-output/planning-artifacts/frontend-prd.md` et les composants ou couches logicielles qui la portent :

| Exigence FR | Libellé synthétique | Écran / Route associée | Composant(s) porteur(s) | Couche technique porteuse | États obligatoires couverts |
|---|---|---|---|---|---|
| FR-AUTH-01 | Connexion utilisateur | `/login` | `LoginForm`, `LoginPage` | `src/features/auth/`, schéma Zod, client HTTP | Chargement, Vide, Erreur, Nominal |
| FR-AUTH-02 | Transmission requêtes protégées | Toutes routes `/cases/*` | `AuthGuard`, `AuthenticatedLayout` | `src/api/client/` (intercepteur Bearer en mémoire vive) | Nominal |
| FR-AUTH-03 | Détection expiration jeton d'accès | Transverse | `AuthInterceptor` | `src/api/client/` (capture réponse HTTP 401) | Nominal (file d'attente transparente) |
| FR-AUTH-04 | Renouvellement silencieux (D6) | Tâche de fond | `SessionManager` | `src/api/client/` (POST `/api/auth/refresh`, rejeu des requêtes) | Nominal (continuité sans rechargement) |
| FR-AUTH-05 | Échec renouvellement session | Transverse vers `/login` | `SessionManager`, `LoginPage` | `src/features/auth/` (purge mémoire, redirection vers `/login`) | Erreur, Accès refusé |
| FR-AUTH-06 | Déconnexion explicite (D6) | TopBar transverse | `TopBarUserMenu` | `src/features/auth/` (POST `/api/auth/logout`, purge mémoire et cache) | Nominal |
| FR-CASES-01 | Consultation paginée et recherche | `/cases` | `CasesTable`, `CasesFilter`, `CasesPage` | `src/features/cases/hooks/useCases.ts` (TanStack Query) | Chargement, Vide, Erreur, Accès refusé, Nominal |
| FR-CASES-02 | Création d'un nouveau dossier | `/cases` (modale) | `CreateCaseModal`, `CreateCaseForm` | `src/features/cases/hooks/useCreateCase.ts`, schéma Zod | Vide/Saisie, Chargement, Erreur, Nominal |
| FR-CTX-01 | Consultation et édition contexte | `/cases/:caseId` | `CaseContextCard`, `CaseMembersList` | `src/features/cases/hooks/useCaseDetail.ts`, `useUpdateCase.ts` | Chargement, Vide, Erreur, Accès refusé, Nominal |
| FR-CTX-02 | Évolution du statut global dossier | `/cases/:caseId` | `CaseStatusSelector` | `src/features/cases/hooks/useUpdateCaseStatus.ts` | Nominal, Erreur |
| FR-EVI-01 | Dépôt et téléversement preuves | `/cases/:caseId/evidence` | `EvidenceDropzone`, `UploadProgressBar` | `src/api/upload/xhrUploader.ts` (XMLHttpRequest streaming) | Vide, Transfert, Refusé, Nominal |
| FR-EVI-02 | Inventaire preuves et suivi ingestion | `/cases/:caseId/evidence` | `EvidenceTable`, `EvidenceStatusBadge` | `src/features/evidence/hooks/useEvidence.ts` (polling 3-5s) | Chargement, Vide, Échec, Altéré, Nominal |
| FR-EVI-03 | Panneau d'inspection d'une preuve | `/cases/:caseId/evidence/:evidenceId` | `EvidenceDetailDrawer`, `Sha256Display` | `src/features/evidence/hooks/useEvidenceDetail.ts` | Chargement, Vide, Erreur, Accès refusé, Nominal |
| FR-PLAN-01 | Consultation du plan Planner | `/cases/:caseId/plan` | `PlanStepsList`, `PlanStepItem` | `src/features/investigation/hooks/usePlan.ts` (polling attente) | Attente, Vide, Erreur, Nominal |
| FR-PLAN-02 | Arbitrage et validation porte H1 | `/cases/:caseId/plan` | `PlanActionBar`, `RejectPlanDialog` | `src/features/investigation/hooks/useArbitratePlan.ts` | Accès refusé, Plan validé (lecture seule) |
| FR-RUN-01 | Supervision temps réel agents | `/cases/:caseId/run` | `AgentGrid`, `AgentCard`, `RunActivityFeed` | `src/features/investigation/hooks/useRunStatus.ts` (polling 2s) | Attente, En cours, Terminé |
| FR-RUN-02 | Contrôle session et relance agent | `/cases/:caseId/run` | `RunControlBar`, `RetryAgentButton` | `src/features/investigation/hooks/useRunControl.ts` | Nominal, Échec partiel |
| FR-RES-01 | Navigation multi-vues résultats | `/cases/:caseId/results` | `ResultsTabsLayout`, `ResultsPage` | `src/features/results/hooks/useResults.ts` | Chargement, Vide, Résultats partiels, Nominal |
| FR-RES-02 | Chronologie unifiée faits techniques | `/cases/:caseId/results` (Chronologie) | `TimelineList`, `TimelineFilterBar` | `src/features/results/hooks/useTimeline.ts` | Nominal, Vide, Filtré |
| FR-RES-03 | Panneau latéral d'inspection source | `/cases/:caseId/results` | `ObservationSourceDrawer` | `src/features/results/hooks/useObservationDetail.ts` | Chargement, Nominal |
| FR-REV-01 | Arbitrage qualitatif findings (H2) | `/cases/:caseId/review` (Porte H2) | `FindingsReviewList`, `FindingCard` | `src/features/review/hooks/useFindings.ts`, `useArbitrateFinding.ts` | Attente, Vide, Nominal |
| FR-REV-02 | Arbitrage confidentialité (H3) | `/cases/:caseId/review` (Porte H3) | `PresidioPreviewCard`, `GateH3ConsentForm` | `src/features/review/hooks/useGateH3.ts` | Externe indisponible, Nominal |
| FR-REP-01 | Compilation et visualisation rapport | `/cases/:caseId/report` | `ReportViewer`, `ReportChapterNav` | `src/features/report/hooks/useGenerateReport.ts` (polling attente) | En génération, Échec, Nominal |
| FR-REP-02 | Historique versions et export scellé | `/cases/:caseId/report` | `ReportHistoryTable`, `ExportButtonsGroup` | `src/features/report/hooks/useReportHistory.ts`, client HTTP | Nominal |

### 8.2 Matrice des Exigences Non Fonctionnelles (NFR)

| Exigence NFR | Thématique | Règle d'architecture appliquée |
|---|---|---|
| NFR-ACC-01 | Contrastes WCAG 2.1 AA | Palette stricte à 5 couleurs : texte mist (`#B7DFDF`) sur ink (`#020C0C`) (ratio 13.80) et teal (`#019F9E`) sur ink (ratio 6.09) conformes AA. Texte deep (`#19595A`) interdit sur ink. Texte cyan sur mist/teal interdit. Aucune exigence AAA. |
| NFR-ACC-02 | Signalement non chromatique | Tous les statuts et sévérités associent impérativement une icône lucide-react et un libellé textuel en majuscules. Aucune couleur seule ne porte de sens. |
| NFR-ACC-03 | Navigation au clavier | Tous les éléments interactifs sont focalisables via Tabulation, actionnables par Entrée/Espace, avec anneau de focus cyan (`#01DBDC`) de 2 pixels. |
| NFR-PERF-01 | First Contentful Paint (FCP) | Architecture statique Vite, découpage de code automatique par route (code-splitting dynamique) ; valeur seuil : à décider (mesure sur environnement de test). |
| NFR-PERF-02 | Réactivité aux interactions | Gestion de l'état d'interface purement local en mémoire vive sans rechargement de page ; seuil temporel : à décider. |
| NFR-PERF-03 | Cadence et arrêt du polling | Conforme ADR-0008 (cadence 3 à 5 secondes pilotée par Retry-After) ; arrêt systématique dès l'atteinte d'un statut terminal ou démontage de vue. |
| NFR-COMPAT-01 | Support navigateurs | Exécution garantie sur versions stables actuelles des moteurs Chromium (Chrome/Edge >= 120), Gecko (Firefox >= 120) et WebKit (Safari >= 17). |
| NFR-RESP-01 | Résolution minimale | Conçu pour affichage bureautique fixe de 1280x720 pixels minimum, sans défilement horizontal. |
| NFR-ERR-01 | Résilience statuts inconnus | Affichage sous la forme « État inconnu (code_brut) » sans interruption ni plantage de l'arbre React ; actions associées désactivées par sécurité. |
| NFR-ERR-02 | Préservation des saisies | Maintien en mémoire vive locale des formulaires actifs en cas d'erreur réseau HTTP 5xx, interdisant toute perte de données. |

---

## 9. Décisions Proposées (Statut « proposée »)

Les décisions listées ci-après sont formellement soumises à l'arbitrage du Team Lead et du Product Lead. Conformément aux directives architecturales, **aucune de ces décisions n'est appliquée dans le présent document** :

| Identifiant | Intitulé de la proposition | Statut | Options envisagées | Recommandation | Impact / Décision attendue |
|---|---|---|---|---|---|
| DP-01 | Mode de rendu des listes massives d'événements dans la chronologie | proposée | Option A : Pagination serveur stricte par blocs de 100 événements.<br>Option B : Virtualisation de liste côté client via TanStack Virtual. | Option A recommandée pour le MVP pour minimiser la complexité d'implémentation. | À trancher avant l'Épic F4 pour dimensionner le composant `TimelineList`. |
| DP-02 | Intégration d'un écran dédié de consultation du journal d'audit immuable (`AuditEvent`) | proposée | Option A : Maintien strict de l'exclusion du MVP (audit persisté en base uniquement).<br>Option B : Ajout d'une vue de consultation simplifiée en lecture seule. | Option A recommandée pour respecter scrupuleusement le périmètre MVP validé. | À trancher avant l'Épic F1 pour stabiliser l'arborescence des routes. |
| DP-03 | Mode de génération et d'extraction des rapports d'incident (formats PDF, Markdown, JSON) | proposée | Option A : Compilation et rendu binaire assurés à 100% par le back-end, le front assurant uniquement le déclenchement et le téléchargement du flux.<br>Option B : Génération PDF hybride côté client via bibliothèque de rendu d'impression. | Option A recommandée pour garantir la reproductibilité et le scellement cryptographique strict du livrable. | À trancher avant l'Épic F5 pour cadrer les endpoints de l'Épic E8. |
| DP-04 | Seuil de troncature volumétrique pour la prévisualisation dans le panneau d'inspection de preuve | proposée | Option A : Plafond fixe à 500 lignes ou 64 Ko d'artefact brut affiché, avec bouton de téléchargement de l'observation intégrale.<br>Option B : Affichage intégral avec pagination interne au panneau latéral. | Option A recommandée pour préserver la mémoire vive du navigateur sur les ruches et images volumineuses. | À trancher avant l'Épic F3 pour calibrer `EvidenceDetailDrawer`. |
| DP-05 | Comportement de relance lors d'une déconnexion prolongée pendant une tâche asynchrone | proposée | Option A : Affichage d'un bandeau persistant de rupture avec tentative automatique de reconnexion toutes les 10 secondes.<br>Option B : Arrêt du polling avec bouton d'actualisation manuelle « Réessayer la connexion ». | Option B recommandée pour éviter les surcharges réseau silencieuses en situation dégradée. | À trancher avant l'Épic F3 pour paramétrer le gestionnaire de scrutation. |
| DP-06 | Prise en compte de la politique de rafraîchissement d'onglet (Page Reload F5) | proposée | Option A : Appel systématique initial de `/api/auth/refresh` au montage de l'application si l'access token mémoire est nul.<br>Option B : Redirection immédiate vers `/login` sans tentative de renouvellement silencieux. | Option A recommandée pour assurer la persistance transparente de session de l'analyste lors d'un rechargement d'onglet. | À trancher avant l'Épic F1 pour finaliser la logique de `AuthGuard`. |

---

## 10. Points « À Décider » et Questions Ouvertes

Les éléments suivants constituent des paramètres chiffrés ou des arbitrages fonctionnels dont la fixation définitive nécessite des mesures expérimentales ou un arbitrage préalable :

1. **Seuil chiffré du délai d'affichage du premier contenu significatif (NFR-PERF-01 - FCP)** : Le seuil de performance cible en millisecondes pour le First Contentful Paint sur station bureautique est : à décider (mesure lors des tests de performance sur les premiers écrans assemblés).
2. **Délai maximal de réactivité aux interactions internes (NFR-PERF-02)** : Le temps de réponse maximal toléré lors d'un basculement d'onglet ou de l'ouverture du tiroir latéral est : à décider.
3. **Plafond volumétrique pour le téléversement unitaire de preuves brutes** : La taille maximale exacte autorisée pour un fichier binaire (image RAM ou ruche de registre volumineuse) sur la Gateway d'ingestion est : à décider en accord avec le calibrage de l'infrastructure de stockage back-end.
4. **Politique d'expiration d'inactivité de l'analyste** : Faut-il introduire un délai d'inactivité au clavier/souris révoquant prématurément le jeton mémoire avant l'échéance des 15 minutes, ou s'en tenir strictement au cycle de vie de 15 minutes sans détection d'inactivité ? Point : à décider.
5. **Emplacement cible définitif du fichier de spécification OpenAPI** : L'adresse de publication du fichier (ex. `docs/contrat-api.yaml` ou endpoint direct d'exposition) est : à décider en concertation avec la piste back-end.

---

*Document d'architecture front-end finalisé pour le périmètre MVP d'IRYX. Arrêt du workflow sans enchaînement sur les épics, dans l'attente de la revue et de la validation formelle par le Team Lead.*
