---
status: validé
project: IRYX-Frontend
version: 1.0.0
created: 2026-11-25
updated: 2026-11-25
author: Master Facilitator (Agent Analyst, Architect & PM)
scope: Front-End MVP
inputDocuments:
  - _bmad-output/planning-artifacts/frontend-prd.md
  - _bmad-output/planning-artifacts/frontend-architecture.md
  - docs/frontend/10-contexte-frontend.md
  - docs/frontend/11-ecrans-et-routes.md
  - docs/frontend/12-parcours-et-etats.md
  - docs/frontend/13-conventions-frontend.md
  - docs/frontend/14-contrat-et-simulation.md
  - docs/adr/ADR-0011-transport-authentification.md
---

# IRYX Front-End - Découpage en Épics et Récits Utilisateurs (Epics & Stories)

---

## 1. Vue d'Ensemble et Cadre d'Exécution

Le présent document constitue la déclinaison opérationnelle exhaustive du Document des Exigences Produit (PRD) et du Document d'Architecture Technique du front-end IRYX en épics et récits utilisateurs (stories) directement actionnables pour les sessions de développement.

### 1.1 Principes Directeurs et Règles de Rédaction

1. Découpage imposé : Cinq épics fonctionnels séquentiels (F1 à F5) matérialisant le canevas d'investigation en cinq étapes et les exigences transverses.
2. Dimensionnement unitaire strict : Chaque récit utilisateur (story) est dimensionné pour être intégralement réalisé et validé en une journée de développement au maximum par un développeur.
3. Structure normalisée des récits : Chaque story respecte le canevas « En tant que [rôle], je veux [action], afin de [bénéfice] », suivi de critères d'acceptation vérifiables rédigés selon le formalisme Étant donné / Quand / Alors / Et (Given / When / Then).
4. Couverture systématique des cinq états obligatoires : Chaque story traite explicitement au minimum ses cinq états fondamentaux d'interface :
   - État de chargement (loading)
   - État vide (empty)
   - État d'erreur (error)
   - État d'accès refusé (forbidden / unauthorized)
   - État nominal (success)
5. Traçabilité des dépendances et contraintes : Chaque story porte explicitement ses mentions normées :
   - Dépendance au contrat back-end : « bloquée par contrat : E<n> » si elle appelle l'API (ou « aucune »).
   - Paramètres d'architecture : « à caler : C<n> » si elle touche un seuil ou une taille listé en C1 à C5 de l'architecture (ou « aucun »).
   - Décisions proposées appliquées : « DP-xx » selon les arbitrages verrouillés DP-01 à DP-06 (ou « aucune »).
6. Respect absolu de la palette stricte à cinq couleurs : Utilisation exclusive des cinq jetons graphiques officiels :
   - #020C0C (ink) : couleur de fond principale et texte sombre inversé
   - #19595A (deep) : bordures, séparateurs et éléments de structure
   - #019F9E (teal) : textes secondaires et statuts neutres
   - #01DBDC (cyan) : actions primaires, focus actif et alertes élevées
   - #B7DFDF (mist) : texte principal et fond papier de rapport
   Aucune autre couleur, nuance ou dénomination chromatique hors palette stricte n'est autorisée.
7. Accessibilité universelle WCAG 2.1 AA : Navigation intégrale au clavier avec anneau de focus cyan (#01DBDC) de 2 pixels, respect rigoureux des ratios de contraste AA (mist sur ink à 13.80, teal sur ink à 6.09, ink sur mist à 13.80), et double signalement non chromatique systématique (libellé textuel en lettres majuscules associé à une icône lucide-react).
8. Absence d'invention de valeurs : Tout paramètre chiffré, durée, seuil ou dimension non encore stabilisé est formellement consigné sous la mention « à décider ».

---

## 2. Inventaire des Exigences et Tableau de Correspondance

### 2.1 Exigences Fonctionnelles (FR-AUTH-01 à FR-REP-02)

| Identifiant FR | Intitulé synthétique de l'exigence | Écran / Route associée | Épic porteur | Stories associées |
|---|---|---|---|---|
| FR-AUTH-01 | Connexion utilisateur | /login | Épic F1 | F1.2 |
| FR-AUTH-02 | Transmission sécurisée des requêtes protégées | Toutes routes /cases/* | Épic F1 | F1.3 |
| FR-AUTH-03 | Détection d'expiration du jeton d'accès | Transverse API client | Épic F1 | F1.3 |
| FR-AUTH-04 | Renouvellement silencieux de la session (D6) | Transverse tâche de fond | Épic F1 | F1.4 |
| FR-AUTH-05 | Gestion de l'échec de renouvellement et expiration | Transverse vers /login | Épic F1 | F1.4 |
| FR-AUTH-06 | Déconnexion explicite sans révocation serveur (D6) | TopBar transverse | Épic F1 | F1.5 |
| FR-CASES-01 | Consultation paginée et recherche des dossiers | /cases | Épic F1 | F1.6 |
| FR-CASES-02 | Création d'un nouveau dossier d'investigation | /cases (modale) | Épic F1 | F1.7 |
| FR-CTX-01 | Consultation et modification du contexte | /cases/:caseId | Épic F2 | F2.1 |
| FR-CTX-02 | Évolution du statut global du dossier | /cases/:caseId | Épic F2 | F2.2 |
| FR-EVI-01 | Dépôt et téléversement de preuves avec progression | /cases/:caseId/evidence | Épic F3 | F3.1 |
| FR-EVI-02 | Inventaire des preuves et suivi d'ingestion | /cases/:caseId/evidence | Épic F3 | F3.2 |
| FR-EVI-03 | Panneau d'inspection détaillée d'une preuve | /cases/:caseId/evidence/:evidenceId | Épic F3 | F3.3 |
| FR-PLAN-01 | Consultation du plan proposé par le Planner | /cases/:caseId/plan | Épic F4 | F4.1 |
| FR-PLAN-02 | Arbitrage et validation formelle de la porte H1 | /cases/:caseId/plan | Épic F4 | F4.2 |
| FR-RUN-01 | Supervision temps réel de l'orchestration des agents | /cases/:caseId/run | Épic F4 | F4.3 |
| FR-RUN-02 | Contrôle de session et reprise sur incident d'agent | /cases/:caseId/run | Épic F4 | F4.4 |
| FR-RES-01 | Navigation multi-vues des résultats | /cases/:caseId/results | Épic F4 | F4.5 |
| FR-RES-02 | Chronologie unifiée des faits techniques | /cases/:caseId/results | Épic F4 | F4.6 |
| FR-RES-03 | Panneau latéral d'inspection de la source | /cases/:caseId/results | Épic F4 | F4.7 |
| FR-REV-01 | Arbitrage qualitatif des findings en porte H2 | /cases/:caseId/review | Épic F4 | F4.8 |
| FR-REV-02 | Arbitrage de confidentialité et porte H3 | /cases/:caseId/review | Épic F4 | F4.9 |
| FR-REP-01 | Compilation et visualisation du rapport d'enquête | /cases/:caseId/report | Épic F5 | F5.1 |
| FR-REP-02 | Historique des versions et export scellé | /cases/:caseId/report | Épic F5 | F5.2 |

Nombre total d'exigences fonctionnelles (FR) : 24.
Nombre d'exigences fonctionnelles couvertes par au moins une story : 24 (100%).
Exigences fonctionnelles sans story : Aucune (liste vide).

### 2.2 Exigences Non Fonctionnelles (NFR)

| Identifiant NFR | Thématique | Couverture par les stories |
|---|---|---|
| NFR-ACC-01 | Conformité des contrastes de couleur WCAG 2.1 AA | F1.1, F1.2, F1.5, F1.6, F1.7, F2.1, F2.2, F3.1, F3.2, F3.3, F4.1 à F4.9, F5.1, F5.2, F5.4 |
| NFR-ACC-02 | Signalement non chromatique des sévérités et statuts | F1.6, F2.2, F3.2, F4.3, F4.4, F4.8, F5.3, F5.4 |
| NFR-ACC-03 | Navigation intégrale au clavier et anneau cyan (#01DBDC) | F1.1, F1.2, F1.5, F1.6, F1.7, F2.1, F2.2, F3.1, F3.2, F3.3, F4.1 à F4.9, F5.1, F5.2, F5.4 |
| NFR-PERF-01 | Délai d'affichage du premier contenu significatif (FCP) : à décider | F1.6, F5.5 |
| NFR-PERF-02 | Délai de réactivité aux interactions internes : à décider | F1.6, F3.3, F4.5, F4.7, F5.5 |
| NFR-PERF-03 | Cadence et arrêt de la scrutation réseau (ADR-0008) | F3.2, F4.1, F4.3, F5.1, F5.5 |
| NFR-COMPAT-01 | Support navigateurs Chromium, Gecko, WebKit | F5.4, F5.5 |
| NFR-RESP-01 | Résolution minimale 1280x720 pixels sans défilement horizontal | F1.1, F1.5, F5.3, F5.5 |
| NFR-ERR-01 | Résilience face aux statuts inconnus sans plantage React | F5.3 |
| NFR-ERR-02 | Préservation des formulaires actifs lors de pannes réseau | F1.7, F2.1, F4.2, F4.8, F5.3 |

### 2.3 Paramètres d'Architecture à Caler (C1 à C5)

| Identifiant | Paramètre architectural | Statut | Responsable proposé (à confirmer) | Stories touchées |
|---|---|---|---|---|
| C1 | Seuil chiffré du délai d'affichage du premier contenu significatif (NFR-PERF-01 - FCP) | à décider | Tech Lead (à confirmer) | F1.6, F5.5 |
| C2 | Délai maximal de réactivité aux interactions internes (NFR-PERF-02) | à décider | Tech Lead (à confirmer) | F1.6, F3.3, F4.5, F4.7, F5.5 |
| C3 | Plafond volumétrique pour le téléversement unitaire de preuves brutes | à décider | Product Lead (à confirmer) | F3.1 |
| C4 | Politique d'expiration d'inactivité de l'analyste | à décider | Product Lead (à confirmer) | F1.3 |
| C5 | Emplacement cible définitif du fichier de spécification OpenAPI | à décider | Tech Lead (à confirmer) | F1.2 |

### 2.4 Décisions Proposées Confirmées et Verrouillées (DP-01 à DP-06)

| Identifiant | Décision confirmée | Description opérationnelle | Stories appliquant la DP |
|---|---|---|---|
| DP-01 | Chronologie en pagination serveur | Pagination serveur par blocs de 100 événements dans la chronologie unifiée | F4.6 (vérifiée par F5.5) |
| DP-02 | Aucun écran d'audit au MVP | Exclusion formelle de tout écran de consultation du journal d'audit au MVP | F1.1, F1.5 (vérifiée par F5.5) |
| DP-03 | Scellement et production back-end | Rapports produits et scellés à 100% par le back-end, le front ne compile rien | F5.1, F5.2 (vérifiée par F5.5) |
| DP-04 | Troncature volumétrique d'artefact | Artefacts bruts tronqués à 500 lignes ou 64 Ko avec téléchargement direct | F3.3, F4.7 (vérifiée par F5.5) |
| DP-05 | Arrêt scrutation sur panne prolongée | Arrêt du polling en cas de coupure prolongée avec bouton « Réessayer la connexion » | F3.2, F4.1, F4.3, F5.1 (vérifiée par F5.5) |
| DP-06 | Renouvellement silencieux initial | Renouvellement silencieux via /api/auth/refresh au chargement de page si token nul | F1.4 (vérifiée par F5.5) |

---

## 3. Liste des Épics Imposés

- Épic F1 : Socle, connexion, shell du dossier, liste des dossiers
- Épic F2 : Contexte du dossier
- Épic F3 : Preuves : dépôt, liste, panneau de détail
- Épic F4 : Plan H1, suivi des agents, résultats, revue H2 et H3
- Épic F5 : Rapport, états d'erreur globaux, accessibilité, parcours de bout en bout

---

## 4. Spécification Détaillée des Épics et Stories

---

### Épic F1 : Socle, connexion, shell du dossier, liste des dossiers

- Objectif de l'épic : Initialiser l'infrastructure applicative front-end, implémenter le mécanisme d'authentification Bearer sécurisé en mémoire vive volatile (sans stockage dans localStorage ni sessionStorage conformément à ADR-0011), le renouvellement silencieux sans état, la déconnexion explicite, le cadre de navigation permanent (TopBar et Shell de dossier à 5 étapes) et la gestion de la liste et de la création de dossiers d'investigation.
- FR couvertes : FR-AUTH-01, FR-AUTH-02, FR-AUTH-03, FR-AUTH-04, FR-AUTH-05, FR-AUTH-06, FR-CASES-01, FR-CASES-02
- Dépendance au contrat back : Épic E1 (Authentification JWT), Épic E2 (Organisations et dossiers)
- Critères de fin d'épic :
  1. L'application Vite/React/TypeScript compile en mode strict sans erreur, avec Tailwind restreint aux cinq couleurs officielles et Mock Service Worker (MSW) opérationnel.
  2. L'écran /login permet l'authentification et acquiert le jeton Bearer (15 minutes) exclusivement en mémoire vive, avec le cookie httpOnly de renouvellement (7 jours).
  3. L'intercepteur réseau injecte le jeton Bearer, suspend les requêtes concurrentes sur code HTTP 401 et exécute le renouvellement silencieux via /api/auth/refresh (ADR-0011).
  4. Le rechargement de page (touche F5) conserve la session de l'analyste par appel silencieux initial sans redirection intempestive (DP-06).
  5. La déconnexion explicite purge l'état mémoire, supprime le cookie côté client et redirige vers /login sans écran d'audit (DP-02).
  6. Le shell permanent expose la TopBar et la barre latérale matérialisant en continu les 5 étapes du dossier d'enquête.
  7. L'écran /cases affiche la liste ordonnée des dossiers sous forme de tableau paginé avec recherche textuelle instantanée.
  8. La modale de création valide les métadonnées selon le schéma Zod et initialise le dossier avec navigation immédiate vers /cases/:caseId.

#### Story F1.1 : Initialisation du socle applicatif front-end et configuration de l'infrastructure
- En tant que : Développeur front-end
- Je veux : Initialiser l'application Vite, TypeScript strict, Tailwind configuré sur la palette stricte, TanStack Query, React Router et MSW
- Afin de : Disposer d'une base technique conforme aux conventions, typée et prête pour le développement déconnecté
- Dépendance contrat : aucune
- Paramètres d'architecture : aucun
- Décisions appliquées : DP-02 (aucun écran d'audit au MVP)
- Critères d'acceptation :
  - État nominal :
    - Étant donné le projet initialisé dans le répertoire frontend/
    - Quand la commande de build Vite est exécutée
    - Alors l'arborescence src/app/, src/pages/, src/features/, src/components/, src/api/, src/lib/ et src/styles/ compile sans avertissement
    - Et la configuration Tailwind interdit toute classe hors palette stricte (#020C0C, #19595A, #019F9E, #01DBDC, #B7DFDF)
    - Et le client TanStack Query est monté avec les valeurs de staleTime et gcTime spécifiées
    - Et la couche MSW dans src/test/mocks/ intercepte les requêtes de test en mode développement
  - État de chargement :
    - Étant donné le montage initial de l'application
    - Quand les modules racines se chargent
    - Alors un indicateur de chargement stylisé aux couleurs du thème s'affiche sans saut graphique
  - État vide :
    - Étant donné une route inexistante sollicitée dans le navigateur
    - Quand le routeur React Router traite l'URL
    - Alors un écran d'erreur 404 neutre est affiché avec un lien de retour vers la racine sans exposer de page d'audit
  - État d'erreur :
    - Étant donné une défaillance de script ou d'initialisation d'un composant racine
    - Quand l'arbre React lève une exception
    - Alors une limite d'erreur (ErrorBoundary) capture l'anomalie et affiche un message générique invitant au rechargement sans rupture d'affichage
  - État d'accès refusé :
    - Étant donné un accès direct à une route protégée sans contexte initialisé
    - Quand le composant AuthGuard s'exécute
    - Alors l'accès est suspendu et la navigation est orientée vers /login

#### Story F1.2 : Formulaire de connexion et acquisition du jeton d'accès
- En tant que : Analyste SOC ou Enquêteur DFIR
- Je veux : Saisir mon identifiant et mon mot de passe sur l'écran /login et valider le formulaire
- Afin de : M'authentifier auprès de l'API et obtenir un jeton d'accès Bearer de 15 minutes en mémoire vive volatile
- Dépendance contrat : bloquée par contrat : E1
- Paramètres d'architecture : à caler : C5 (emplacement cible définitif du fichier de spécification OpenAPI : à décider)
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné un opérateur sur l'écran /login
    - Quand il saisit des identifiants valides et valide le formulaire
    - Alors une requête POST est émise vers l'endpoint d'authentification de l'API
    - Et le jeton d'accès Bearer est enregistré exclusivement en mémoire vive applicative dans src/api/client/
    - Et aucun jeton n'est écrit dans localStorage ni sessionStorage
    - Et le cookie httpOnly de renouvellement est positionné par le serveur pour 7 jours
    - Et l'analyste est automatiquement redirigé vers l'écran /cases
  - État de chargement :
    - Étant donné le formulaire de connexion en cours de soumission
    - Quand la requête d'authentification est en transit
    - Alors les champs de saisie et le bouton de connexion sont désactivés
    - Et le bouton affiche un indicateur visuel de progression
  - État vide :
    - Étant donné l'affichage initial de la page /login
    - Quand aucun champ n'est encore renseigné
    - Alors les champs adresse électronique et mot de passe sont vierges avec focus positionné sur le premier champ
    - Et le bouton de soumission est interactif
  - État d'erreur :
    - Étant donné la saisie d'identifiants incorrects ou une coupure de communication avec le serveur
    - Quand l'API retourne un code HTTP 401 ou 5xx
    - Alors un message d'erreur textuel unique « Identifiants incorrects » s'affiche sans vider le champ identifiant
    - Et en cas d'erreur réseau, la mention « Serveur injoignable. Veuillez vérifier votre connexion. » apparaît
  - État d'accès refusé :
    - Étant donné un compte utilisateur désactivé ou verrouillé par l'administrateur
    - Quand l'authentification est rejetée avec un statut 403
    - Alors le message explicite « Compte inactif ou accès révoqué. Contactez votre administrateur. » s'affiche

#### Story F1.3 : Client réseau sécurisé, intercepteur Bearer et détection d'expiration 401
- En tant que : Enquêteur DFIR
- Je veux : Que mes requêtes vers l'API portent automatiquement mon jeton d'accès Bearer et que les erreurs 401 soient interceptées de manière transparente
- Afin de : Garantir la sécurité des communications sans exposer le jeton dans le stockage du navigateur et suspendre les appels lors d'une expiration
- Dépendance contrat : bloquée par contrat : E1
- Paramètres d'architecture : à caler : C4 (politique d'expiration d'inactivité de l'analyste : à décider)
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné une requête métier émise par un hook TanStack Query
    - Quand le client openapi-fetch intercepte l'appel sortant
    - Alors l'en-tête HTTP Authorization: Bearer est injecté avec le jeton d'accès actif présent en mémoire vive
    - Et la requête est transmise sans altération de la charge utile
  - État de chargement :
    - Étant donné plusieurs requêtes sortantes émises simultanément lors de l'expiration du jeton d'accès (après 15 minutes)
    - Quand le code HTTP 401 est détecté par l'intercepteur
    - Alors les requêtes concurrentes sont mises en attente dans une file d'attente mémoire sans générer d'échec pour l'utilisateur
  - État vide :
    - Étant donné l'état de repos du client réseau
    - Quand aucune requête n'est en transit
    - Alors la file d'attente d'interception est vide et n'occupe aucune ressource
  - État d'erreur :
    - Étant donné une requête métier renvoyant une erreur HTTP 5xx ou une coupure de transport
    - Quand la réponse est réceptionnée
    - Alors l'erreur est propagée au gestionnaire TanStack Query sans déclencher d'invalidation injustifiée du jeton d'accès
  - État d'accès refusé :
    - Étant donné un jeton d'accès structurellement corrompu ou falsifié
    - Quand l'API renvoie immédiatement 401 sans possibilité de validation
    - Alors l'intercepteur prépare l'éviction sans boucle infinie

#### Story F1.4 : Renouvellement silencieux de session, échec d'éviction et réarmement au chargement
- En tant que : Analyste SOC
- Je veux : Bénéficier d'un renouvellement silencieux de mon jeton d'accès via /api/auth/refresh lors d'un 401 ou au rechargement de la page, et être redirigé vers la connexion si mon renouvellement échoue
- Afin de : Travailler sans interruption de session tant que mon jeton de renouvellement de 7 jours est valide, tout en garantissant la sécurité de mon poste
- Dépendance contrat : bloquée par contrat : E1
- Paramètres d'architecture : aucun
- Décisions appliquées : DP-06 (renouvellement silencieux de /api/auth/refresh au chargement de la page si le jeton d'accès est absent)
- Critères d'acceptation :
  - État nominal :
    - Étant donné l'interception d'une réponse 401 sur une requête métier ou l'arrivée sur l'application avec jeton mémoire nul (touche F5)
    - Quand le gestionnaire de session émet une requête asynchrone POST vers /api/auth/refresh avec contrôle de l'en-tête Origin
    - Alors le navigateur transmet automatiquement le cookie httpOnly de renouvellement
    - Et le back-end valide la signature sans consultation de base ni rotation du refresh token (modèle D6)
    - Et le nouvel access token de 15 minutes est enregistré en mémoire vive volatile
    - Et les requêtes suspendues dans la file d'attente sont rejouées avec succès sans scintillement pour l'analyste
  - État de chargement :
    - Étant donné le processus de renouvellement silencieux en cours
    - Quand la requête /api/auth/refresh est en cours d'exécution
    - Alors l'affichage courant de l'interface reste figé sur son état précédent sans rupture d'affichage
  - État vide :
    - Étant donné une réinitialisation de session suite à une expiration
    - Quand la mémoire vive est purgée
    - Alors aucune donnée résiduelle de session ne subsiste dans localStorage ni sessionStorage
  - État d'erreur :
    - Étant donné une défaillance réseau ponctuelle lors de la tentative de renouvellement
    - Quand le serveur est momentanément injoignable
    - Alors le client effectue un réessai temporisé avant de prononcer l'échec définitif
  - État d'accès refusé :
    - Étant donné l'échec de renouvellement consécutif à l'expiration des 7 jours du refresh token ou à un cookie invalide (HTTP 401 sur /api/auth/refresh)
    - Quand l'erreur de renouvellement est constatée
    - Alors le jeton d'accès est immédiatement purgé de la mémoire vive
    - Et le cache TanStack Query est intégralement réinitialisé
    - Et l'analyste est redirigé vers /login avec la notification toast « Session expirée. Veuillez vous reconnecter. »
    - Et l'URL couramment consultée est conservée dans l'état de navigation pour réorientation après ré-authentification

#### Story F1.5 : Layout permanent, TopBar, déconnexion explicite et Shell du dossier
- En tant que : Enquêteur DFIR
- Je veux : Disposer d'une TopBar permanente avec mon profil et l'action de déconnexion, ainsi que d'une barre latérale matérialisant les 5 étapes du canevas d'investigation
- Afin de : Me repérer continuellement dans la progression du dossier et me déconnecter de manière sécurisée en purgeant mes données locales
- Dépendance contrat : bloquée par contrat : E1 (pour l'action de déconnexion)
- Paramètres d'architecture : aucun
- Décisions appliquées : DP-02 (aucun écran d'audit au MVP)
- Critères d'acceptation :
  - État nominal :
    - Étant donné un analyste authentifié accédant à /cases/:caseId
    - Quand le composant AuthenticatedLayout et CaseShellLayout sont instanciés
    - Alors la TopBar affiche le logo IRYX, le nom de l'organisation, l'identifiant et le rôle de l'utilisateur, et le bouton « Se déconnecter »
    - Et la barre latérale affiche les cinq étapes : Contexte, Preuves, Plan et agents, Résultats, Revue et rapport
    - Et chaque étape indique son état courant (non démarrée, en cours, terminée, bloquée par une porte)
    - Et aucun lien de navigation vers un écran d'audit n'est présent (DP-02)
    - Et le clic sur « Se déconnecter » appelle POST /api/auth/logout, purge la mémoire volatile, réinitialise le cache et redirige vers /login
  - État de chargement :
    - Étant donné l'accès initial à un dossier
    - Quand les métadonnées de cadrage du dossier sont en cours de récupération
    - Alors des squelettes animés occupent les emplacements de titre et de statut dans le shell
  - État vide :
    - Étant donné la consultation de l'application hors du contexte d'un dossier (/cases)
    - Quand le layout racine est affiché
    - Alors la TopBar est active et la zone centrale présente le tableau général sans barre latérale de dossier
  - État d'erreur :
    - Étant donné l'échec réseau de l'appel POST /api/auth/logout lors d'une déconnexion
    - Quand l'API ne répond pas
    - Alors le front-end force la purge locale de la mémoire vive, détruit le cache et redirige impérativement vers /login pour garantir la sécurité de l'opérateur
  - État d'accès refusé :
    - Étant donné une tentative d'accès au shell sans authentification valide
    - Quand le composant AuthGuard analyse la requête
    - Alors l'accès au shell est immédiatement refusé et l'opérateur est redirigé vers /login

#### Story F1.6 : Consultation paginée et recherche textuelle des dossiers
- En tant que : Analyste SOC ou Enquêteur DFIR
- Je veux : Consulter la liste des dossiers d'investigation sous forme de tableau paginé côté serveur et filtrer dynamiquement par titre
- Afin de : Repérer rapidement un dossier d'enquête et accéder à son espace de travail
- Dépendance contrat : bloquée par contrat : E2
- Paramètres d'architecture : à caler : C1 (seuil chiffré du délai d'affichage FCP : à décider), à caler : C2 (délai maximal de réactivité aux interactions : à décider)
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné un analyste sur la route /cases
    - Quand la liste des dossiers est chargée depuis l'API
    - Alors le tableau affiche pour chaque dossier : titre, statut d'avancement, date de détection UTC et nombre de preuves scellées
    - Et le composant de pagination permet de naviguer de page en page
    - Et la saisie dans le champ de recherche textuelle déclenche une actualisation filtrée des dossiers
    - Et le clic sur une ligne oriente vers la vue /cases/:caseId
  - État de chargement :
    - Étant donné la récupération des dossiers en cours par le hook useCases
    - Quand la réponse serveur est attendue
    - Alors des lignes de squelettes animées remplacent les lignes du tableau
  - État vide :
    - Étant donné une organisation ne comportant aucun dossier d'investigation ou une recherche sans correspondance
    - Quand la liste retournée est vide
    - Alors le message explicite « Aucun dossier d'investigation enregistré. Créez votre premier dossier. » est affiché avec le bouton d'action principal « Nouveau dossier »
  - État d'erreur :
    - Étant donné une défaillance de l'API lors de la récupération des dossiers
    - Quand l'appel retourne une erreur HTTP 5xx
    - Alors une bannière d'alerte indique l'échec de chargement et met à disposition un bouton « Réessayer »
  - État d'accès refusé :
    - Étant donné une requête rejetée avec le code HTTP 403 Forbidden
    - Quand l'analyste n'a pas accès à l'organisation
    - Alors un message d'interdiction est affiché et l'analyste est invité à contacter son administrateur

#### Story F1.7 : Création d'un nouveau dossier d'investigation en modale
- En tant que : Enquêteur DFIR
- Je veux : Ouvrir une fenêtre modale, renseigner les informations de l'affaire et valider la création
- Afin de : Déclarer un nouveau dossier d'investigation et être orienté immédiatement vers son contexte
- Dépendance contrat : bloquée par contrat : E2
- Paramètres d'architecture : aucun
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné un analyste sur l'écran /cases
    - Quand il clique sur le bouton « Nouveau dossier », remplit les champs obligatoires (titre, description, date d'incident, typologie, systèmes affectés) conformes au schéma Zod et soumet
    - Alors une requête POST /api/cases est émise
    - Et à la réception du succès, la modale se ferme, une notification toast confirme la création et l'application navigue vers /cases/:caseId
  - État de chargement :
    - Étant donné la modale en cours de validation serveur
    - Quand la requête de création est en cours
    - Alors le bouton de validation affiche un indicateur de chargement et l'ensemble des champs du formulaire est désactivé
  - État vide :
    - Étant donné l'ouverture de la modale de création
    - Quand le formulaire est affiché
    - Alors les champs textuels sont vides, la date courante UTC est pré-remplie par défaut et le focus est placé sur le champ titre
  - État d'erreur :
    - Étant donné la saisie de données non conformes au schéma Zod ou un rejet 400 de l'API
    - Quand l'utilisateur tente de valider
    - Alors les libellés d'erreur de validation s'affichent sous chaque champ concerné
    - Et les textes saisis restent conservés en mémoire sans perte en cas d'erreur serveur (NFR-ERR-02)
  - État d'accès refusé :
    - Étant donné un profil utilisateur non autorisé à créer un dossier
    - Quand l'API renvoie une réponse 403
    - Alors la modale affiche la notification « Vous n'avez pas les autorisations nécessaires pour créer un dossier dans cette organisation. »

---

### Épic F2 : Contexte du dossier

- Objectif de l'épic : Mettre à disposition de l'enquêteur l'espace de consultation et de pilotage du contexte du dossier d'investigation (Étape 1 du canevas), permettant la modification en ligne des informations administratives, la visualisation en lecture seule des membres autorisés, et l'arbitrage du statut global de l'enquête avec synchronisation temps réel du shell.
- FR couvertes : FR-CTX-01, FR-CTX-02
- Dépendance au contrat back : Épic E2 (Organisations, dossiers et membres)
- Critères de fin d'épic :
  1. L'écran /cases/:caseId restitue l'ensemble des métadonnées du dossier ainsi que la liste des membres autorisés en lecture seule.
  2. Le mode d'édition en ligne permet la mise à jour immédiate du titre et de la description avec validation Zod.
  3. Le sélecteur de statut d'avancement modifie le cycle de vie du dossier (open, in_progress, review, closed) et répercute instantanément le nouvel état sur le badge d'en-tête et la barre latérale.

#### Story F2.1 : Consultation et édition en ligne du contexte administratif et technique du dossier
- En tant que : Enquêteur DFIR
- Je veux : Consulter les métadonnées de mon dossier sur /cases/:caseId et modifier le titre et la description en ligne
- Afin de : Documenter précisément l'enquête et maintenir à jour la qualification de l'incident
- Dépendance contrat : bloquée par contrat : E2
- Paramètres d'architecture : aucun
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné un analyste habilité sur la vue /cases/:caseId
    - Quand la fiche de contexte est affichée
    - Alors le titre, la description, la date de création UTC, le dernier horodatage d'activité et la liste des membres sont visibles
    - Et le clic sur le bouton d'édition permet de modifier le titre et la description
    - Et la sauvegarde émet une requête PATCH /api/cases/:caseId qui actualise immédiatement les données affichées
  - État de chargement :
    - Étant donné l'accès à la route /cases/:caseId
    - Quand les détails du dossier sont interrogés
    - Alors des blocs de squelettes animés remplacent les libellés et zones de texte
  - État vide :
    - Étant donné un dossier ne comportant pas de description ou sans systèmes affectés spécifiés
    - Quand la vue est restituée
    - Alors la mention textuelle par défaut « Aucune description fournie » s'affiche en couleur teal (#019F9E)
  - État d'erreur :
    - Étant donné une erreur réseau ou serveur lors du chargement ou de la sauvegarde des modifications
    - Quand l'API renvoie un statut 5xx
    - Alors une notification d'échec s'affiche avec un bouton « Réessayer » et les saisies en cours restent conservées (NFR-ERR-02)
  - État d'accès refusé :
    - Étant donné un analyste qui n'est pas membre habilité sur le dossier sollicité
    - Quand l'API renvoie un code HTTP 403 Forbidden
    - Alors la vue bloque l'affichage des informations sensibles, affiche la notification « Vous n'avez pas accès à ce dossier » et redirige automatiquement vers /cases

#### Story F2.2 : Gestion de l'évolution du statut global du dossier
- En tant que : Enquêteur DFIR ou Responsable Sécurité
- Je veux : Modifier le statut global d'avancement du dossier via un sélecteur contrôlé
- Afin de : Refléter l'étape courante de l'enquête (open, in_progress, review, closed) et synchroniser l'ensemble des indicateurs de l'interface
- Dépendance contrat : bloquée par contrat : E2
- Paramètres d'architecture : aucun
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné un analyste titulaire sur la fiche de contexte /cases/:caseId
    - Quand il sélectionne un nouveau statut dans le sélecteur (valeurs autorisées : open, in_progress, review, closed)
    - Alors une mutation PATCH /api/cases/:caseId est exécutée
    - Et à la validation serveur, le badge d'état de l'en-tête s'actualise avec libellé en majuscules et icône lucide-react associée
    - Et les clés de requêtes TanStack Query associées sont invalidées pour actualiser la barre latérale
  - État de chargement :
    - Étant donné la mise à jour du statut en cours d'enregistrement
    - Quand la mutation est en vol
    - Alors le sélecteur de statut est temporairement désactivé avec un indicateur discret de synchronisation
  - État vide :
    - Étant donné un dossier dont le statut retourné par l'API n'est pas défini
    - Quand le composant analyse l'état
    - Alors le statut est affiché par défaut sous la mention « NON DÉFINI » avec icône neutre
  - État d'erreur :
    - Étant donné un incident réseau lors de la mise à jour du statut
    - Quand l'API retourne une erreur
    - Alors une notification toast signale l'échec de la mise à jour et le sélecteur se repositionne sur la valeur précédente sans incohérence
  - État d'accès refusé :
    - Étant donné un utilisateur disposant d'un accès en lecture seule
    - Quand il consulte la fiche de contexte
    - Alors le sélecteur de statut est rendu en mode texte non modifiable (lecture seule) sans contrôle interactif

---

### Épic F3 : Preuves : dépôt, liste, panneau de détail

- Objectif de l'épic : Mettre en œuvre l'Étape 2 du canevas d'investigation en fournissant une zone de téléversement lourd avec mesure de progression en streaming (XMLHttpRequest), un registre d'inventaire des preuves avec scrutation périodique de l'état d'ingestion et vérification du scellement SHA-256, ainsi qu'un panneau latéral coulissant d'inspection approfondie synchronisé avec l'URL.
- FR couvertes : FR-EVI-01, FR-EVI-02, FR-EVI-03
- Dépendance au contrat back : Épic E3 (Preuves, scellement et Celery)
- Critères de fin d'épic :
  1. La zone de glisser-déposer gère l'envoi simultané de fichiers multiples (EVTX, logs, ruches, Prefetch, images RAM) avec jauges de progression individuelles précises en pourcentage.
  2. Le registre des preuves affiche les empreintes SHA-256 tronquées et surveille l'ingestion par scrutation REST (3 à 5 secondes).
  3. Le bouton « Lancer l'analyse » est conditionné formellement : actif uniquement si au moins une preuve est à l'état intègre (completed).
  4. Le panneau latéral coulissant (/cases/:caseId/evidence/:evidenceId) s'ouvre sans quitter la liste, restitue l'empreinte complète en chasse fixe et applique la troncature à 500 lignes ou 64 Ko avec téléchargement direct (DP-04).
  5. En cas de coupure réseau prolongée pendant l'ingestion, la scrutation s'arrête avec proposition d'un bouton « Réessayer la connexion » (DP-05).

#### Story F3.1 : Dépôt et téléversement de preuves avec suivi de progression en streaming
- En tant que : Analyste SOC ou Enquêteur DFIR
- Je veux : Déposer par glisser-déposer ou sélection un ou plusieurs fichiers de preuves et suivre leur téléversement en pourcentage individuel
- Afin de : Transférer des volumes forensiques lourds avec visibilité exacte sur l'avancement et pouvoir annuler un envoi si nécessaire
- Dépendance contrat : bloquée par contrat : E3
- Paramètres d'architecture : à caler : C3 (plafond volumétrique pour le téléversement unitaire de preuves brutes : à décider)
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné un opérateur sur l'écran /cases/:caseId/evidence
    - Quand il dépose un ou plusieurs fichiers aux formats autorisés (EVTX, logs texte, ruches de registre, Prefetch, images RAM)
    - Alors le module d'encapsulation XMLHttpRequest initie les flux de téléversement individuels
    - Et chaque fichier affiche sa propre barre de progression avec le pourcentage calculé en temps réel
    - Et à la fin du transfert, le fichier bascule dans le registre à l'état pending pour ingestion Celery
  - État de chargement :
    - Étant donné un ou plusieurs fichiers en cours de transmission
    - Quand le transfert est actif
    - Alors chaque élément en cours expose un bouton individuel « Annuler » permettant d'interrompre la requête XHR immédiatement
  - État vide :
    - Étant donné l'accès initial au registre sans dépôt en cours
    - Quand l'opérateur consulte la zone de dépôt
    - Alors la zone d'accueil met en avant les formats de fichiers pris en charge et le plafond volumétrique unitaire : à décider
  - État d'erreur :
    - Étant donné le dépôt d'un fichier au format non supporté ou excédant le plafond volumétrique : à décider
    - Quand l'analyse préalable du fichier est exécutée côté client
    - Alors le fichier est rejeté immédiatement avec un message descriptif sans émission de requête réseau
    - Et si le transfert échoue en cours de route, la jauge affiche la mention « ÉCHEC DE TRANSFERT » avec possibilité de relance
  - État d'accès refusé :
    - Étant donné un utilisateur non habilité à modifier le dossier
    - Quand il accède à l'écran des preuves
    - Alors la zone de dépôt est désactivée et masquée, seul le tableau en lecture seule restant consultable

#### Story F3.2 : Registre d'inventaire des preuves, suivi d'ingestion par scrutation et condition d'analyse
- En tant que : Enquêteur DFIR
- Je veux : Consulter l'inventaire des preuves scellées, suivre l'état d'ingestion par scrutation et n'activer le lancement d'analyse que si une preuve est intègre
- Afin de : Garantir la chaîne de possession cryptographique et interdire l'analyse sur des éléments corrompus
- Dépendance contrat : bloquée par contrat : E3
- Paramètres d'architecture : aucun
- Décisions appliquées : DP-05 (arrêt de l'interrogation en cas de coupure prolongée, avec bouton « Réessayer la connexion »)
- Justification DP-05 : La story F3.2 assure le suivi d'ingestion des preuves par scrutation périodique (cadence 3 à 5 secondes pilotée par Retry-After selon ADR-0008) sur /cases/:caseId/evidence ; en cas de coupure réseau prolongée, la scrutation s'arrête et le bouton « Réessayer la connexion » est affiché conformément à DP-05.
- Critères d'acceptation :
  - État nominal :
    - Étant donné un dossier comportant des preuves en cours d'ingestion
    - Quand le hook useEvidence interroge l'API par scrutation REST (cadence 3 à 5 secondes pilotée par Retry-After selon ADR-0008)
    - Alors le tableau affiche : nom du fichier, format détecté, taille en octets, empreinte SHA-256 tronquée avec bouton de copie, horodatage UTC et badge de statut d'ingestion
    - Et dès que l'ingestion atteint l'état completed, la preuve est marquée « INTÈGRE » et la scrutation sur cette preuve s'arrête
    - Et le bouton « Lancer l'analyse » devient interactif dès qu'au moins une preuve est intègre (completed)
  - État de chargement :
    - Étant donné la synchronisation initiale ou l'attente d'une réponse de scrutation
    - Quand les données sont interrogées
    - Alors un indicateur visuel discret signale la synchronisation sans masquer le tableau existant
  - État vide :
    - Étant donné un dossier ne comportant encore aucune preuve déposée
    - Quand le registre est consulté
    - Alors le message central « Aucune preuve déposée pour ce dossier » est affiché
    - Et le bouton « Lancer l'analyse » est grisé et désactivé avec infobulle explicative
  - État d'erreur :
    - Étant donné une divergence d'empreinte cryptographique détectée par le serveur ou un échec de tâche Celery
    - Quand le statut passe à failed ou non intègre
    - Alors la ligne est signalée par le libellé « ÉCHEC » ou « NON INTÈGRE » associé à une icône d'alerte lucide-react
    - Et la preuve altérée est exclue de toute sélection d'analyse
    - Et en cas de coupure réseau prolongée, la scrutation s'interrompt et un bouton « Réessayer la connexion » s'affiche (DP-05)
  - État d'accès refusé :
    - Étant donné une session expirée ou un accès non autorisé
    - Quand la requête de scrutation retourne un code 401 ou 403
    - Alors le cycle de scrutation s'interrompt immédiatement et le gestionnaire de sécurité prend le relais

#### Story F3.3 : Panneau d'inspection détaillée d'une preuve et troncature volumétrique
- En tant que : Enquêteur DFIR
- Je veux : Cliquer sur une ligne de preuve pour ouvrir un tiroir coulissant synchronisé avec l'URL et consulter l'empreinte intégrale ainsi que les métadonnées forensiques
- Afin de : Vérifier minutieusement l'intégrité de la preuve sans perdre le contexte du registre et télécharger l'extrait brut
- Dépendance contrat : bloquée par contrat : E3
- Paramètres d'architecture : à caler : C2 (délai maximal de réactivité à l'ouverture du tiroir : à décider)
- Décisions appliquées : DP-04 (artefacts tronqués à 500 lignes ou 64 Ko, avec téléchargement direct)
- Critères d'acceptation :
  - État nominal :
    - Étant donné l'analyste consultant le registre des preuves sur /cases/:caseId/evidence
    - Quand il clique sur une preuve
    - Alors l'application navigue vers la route imbriquée /cases/:caseId/evidence/:evidenceId
    - Et un panneau latéral coulissant s'ouvre à droite de l'écran tout en conservant la liste des preuves visible
    - Et le panneau affiche l'empreinte SHA-256 intégrale en typographie à chasse fixe, l'historique d'ingestion et le décompte d'observations
    - Et si l'observation brute dépasse 500 lignes ou 64 Ko, l'aperçu est tronqué à 500 lignes / 64 Ko avec le bouton « Télécharger l'observation intégrale » (DP-04)
    - Et la fermeture du panneau réoriente l'URL vers /cases/:caseId/evidence
  - État de chargement :
    - Étant donné l'ouverture du panneau latéral
    - Quand les métadonnées forensiques détaillées sont en cours de chargement
    - Alors des squelettes animés occupent les sections du panneau
  - État vide :
    - Étant donné une preuve valide dont le traitement d'ingestion n'a extrait aucune observation technique
    - Quand le panneau s'affiche
    - Alors la mention textuelle « Aucune observation extraite pour cette preuve » apparaît
  - État d'erreur :
    - Étant donné une défaillance de chargement des métadonnées détaillées
    - Quand l'API retourne une erreur
    - Alors un message d'échec est présenté dans le tiroir avec un bouton de réactualisation
  - État d'accès refusé :
    - Étant donné une URL directe vers une preuve d'un dossier dont l'analyste n'est pas membre
    - Quand la vue est sollicitée
    - Alors le tiroir ne s'ouvre pas, un toast d'accès refusé s'affiche et l'utilisateur reste sur la liste autorisée

---

### Épic F4 : Plan H1, suivi des agents, résultats, revue H2 et H3

- Objectif de l'épic : Déployer le cœur opérationnel de l'investigation couvrant les Étapes 3, 4 et 5 (partielle) : examen du plan proposé par le Planner, arbitrage formel franchissant la porte H1, console de supervision en temps réel des agents avec actions de contrôle et relance unitaire, exploration multi-vues des résultats avec chronologie unifiée en pagination serveur de 100 événements (DP-01) et inspection des sources, arbitrage qualitatif des findings en porte H2 bloquant le rapport tant qu'aucun finding n'est validé, et consentement de pseudonymisation en porte H3 autorisant la transmission externe.
- FR couvertes : FR-PLAN-01, FR-PLAN-02, FR-RUN-01, FR-RUN-02, FR-RES-01, FR-RES-02, FR-RES-03, FR-REV-01, FR-REV-02
- Dépendance au contrat back : Épic E4 (Gateway outils), Épic E5 (LangGraph / H1), Épic E6 (Findings / H2), Épic E7 (Chronologie)
- Critères de fin d'épic :
  1. L'écran /cases/:caseId/plan permet la consultation du plan, la suppression d'étapes superflues, le rejet motivé ou la validation formelle scellant la porte H1 en lecture seule immuable avec horodatage UTC et identifiant d'analyste.
  2. L'écran /cases/:caseId/run affiche les cartes dynamiques des 6 agents, le journal d'activité UTC et permet la suspension, la reprise, l'annulation et la relance sélective d'un agent défaillant.
  3. L'écran /cases/:caseId/results propose les trois onglets (Chronologie, Artefacts, Hypothèses) avec bandeau d'alerte permanent en cas de résultats partiels consécutifs à l'échec d'un agent.
  4. La chronologie unifiée est paginée par tranches de 100 événements côté serveur (DP-01) avec filtres par source et plage temporelle UTC.
  5. Le clic sur une source ouvre un tiroir latéral présentant l'observation brute, l'offset et le SHA-256 avec troncature à 500 lignes / 64 Ko et téléchargement direct (DP-04).
  6. L'écran /cases/:caseId/review gère l'arbitrage qualitatif unitaire des findings en porte H2 et interdit l'accès au rapport tant qu'au moins un finding n'est pas validé.
  7. La porte H3 affiche la prévisualisation pseudonymisée Microsoft Presidio, requiert une case à cocher obligatoire pour l'envoi externe et fournit l'option de secours « Générer le rapport en local ».

#### Story F4.1 : Consultation de la séquence d'investigation proposée par l'agent Planner
- En tant que : Enquêteur DFIR
- Je veux : Consulter sur /cases/:caseId/plan la séquence d'étapes forensiques élaborée par le Planner
- Afin de : Prendre connaissance des outils forensiques et des preuves ciblées avant toute validation d'exécution
- Dépendance contrat : bloquée par contrat : E5
- Paramètres d'architecture : aucun
- Décisions appliquées : DP-05 (arrêt de l'interrogation en cas de coupure prolongée, avec bouton « Réessayer la connexion »)
- Justification DP-05 : La story F4.1 interroge un état asynchrone (scrutation régulière de l'élaboration du plan par l'agent Planner sur /cases/:caseId/plan tant que le plan n'est pas finalisé) ; en cas de rupture de connectivité prolongée pendant cette attente, la scrutation s'interrompt et le bouton « Réessayer la connexion » est affiché conformément à DP-05.
- Critères d'acceptation :
  - État nominal :
    - Étant donné un dossier avec preuves intègres dont l'analyse a été déclenchée
    - Quand l'analyste consulte l'écran /cases/:caseId/plan
    - Alors le plan s'affiche sous forme d'une liste ordonnée d'étapes techniques
    - Et chaque étape expose : numéro d'ordre, objectif d'analyse, agent assigné, outil forensique requis (analyseur EVTX, regipy, Volatility 3, etc.) et preuves ciblées
  - État de chargement / attente :
    - Étant donné le Planner en cours d'élaboration de la stratégie
    - Quand la réponse n'est pas encore disponible
    - Alors un écran d'attente animé avec la mention « Élaboration du plan par le Planner en cours... » s'actualise par scrutation
  - État vide :
    - Étant donné un ensemble de preuves ne permettant l'application d'aucun outil forensique
    - Quand le Planner termine sans étapes
    - Alors la notification « Aucun outil forensique applicable aux preuves disponibles » est affichée avec un bouton invitant à déposer d'autres preuves
  - État d'erreur :
    - Étant donné une défaillance de l'agent Planner
    - Quand l'API renvoie un statut d'erreur
    - Alors un message explicite indique la cause de l'incident avec un bouton « Réessayer la planification »
    - Et en cas de rupture de connectivité prolongée, la scrutation s'arrête avec le bouton « Réessayer la connexion » (DP-05)
  - État d'accès refusé :
    - Étant donné un utilisateur non autorisé sur le dossier
    - Quand il sollicite la route du plan
    - Alors l'accès est bloqué avec redirection vers /cases

#### Story F4.2 : Arbitrage unitaire et validation formelle de la porte H1
- En tant que : Enquêteur DFIR
- Je veux : Supprimer des étapes superflues, refuser le plan avec motif obligatoire ou valider formellement la séquence
- Afin de : Franchir la porte humaine H1 en scellant le plan de manière immuable et déclencher la session d'exécution
- Dépendance contrat : bloquée par contrat : E5
- Paramètres d'architecture : aucun
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné un plan proposé soumis à l'arbitrage
    - Quand l'analyste supprime une étape unitaire ou clique sur « Valider le plan (Porte H1) »
    - Alors une mutation POST /api/cases/:caseId/plan/validate est émise
    - Et le plan devient strictement en lecture seule immuable
    - Et l'écran affiche le badge scellé « Plan validé par [Analyste] le [Date UTC] »
    - Et la navigation bascule automatiquement vers la console d'exécution /cases/:caseId/run
  - État de chargement :
    - Étant donné l'action de validation ou de rejet en cours de soumission
    - Quand l'appel réseau est actif
    - Alors les boutons d'action sont désactivés avec indicateur de traitement
  - État vide :
    - Étant donné un plan sans étapes sélectionnées
    - Quand l'analyste consulte l'écran
    - Alors le bouton de validation générale est désactivé
  - État d'erreur :
    - Étant donné le refus du plan sans motif textuel ou une erreur serveur lors de la validation
    - Quand l'action est déclenchée
    - Alors le champ motif est signalé en erreur obligatoire si vide
    - Et en cas d'erreur API, le motif saisi reste préservé en mémoire (NFR-ERR-02)
  - État d'accès refusé :
    - Étant donné un profil utilisateur disposant d'un droit de consultation seule (non analyste)
    - Quand il accède à l'écran du plan
    - Alors les actions de suppression, validation ou rejet sont masquées de l'interface

#### Story F4.3 : Console de supervision en temps réel de l'orchestration des agents
- En tant que : Analyste SOC ou Enquêteur DFIR
- Je veux : Suivre sur /cases/:caseId/run l'état de chaque agent spécialisé et le flux d'activité global horodaté UTC
- Afin de : Visualiser l'avancement des investigations automatisées en temps réel et identifier les phases d'analyse
- Dépendance contrat : bloquée par contrat : E5
- Paramètres d'architecture : aucun
- Décisions appliquées : DP-05 (arrêt de l'interrogation en cas de coupure prolongée, avec bouton « Réessayer la connexion »)
- Justification DP-05 : La story F4.3 assure la supervision temps réel par scrutation périodique de l'activité des agents sur /cases/:caseId/run ; en cas de coupure réseau prolongée, la scrutation s'arrête et le bouton « Réessayer la connexion » est affiché conformément à DP-05.
- Critères d'acceptation :
  - État nominal :
    - Étant donné une session d'exécution active après franchissement de la porte H1
    - Quand la console /cases/:caseId/run s'affiche
    - Alors une grille présente les cartes des agents (Planner, Executor, Analyst, Verifier, Corrélateur, Rapporteur)
    - Et chaque carte affiche son statut dynamique (pending, active, completed, failed), sa jauge d'avancement et son dernier message
    - Et un panneau latéral fait défiler le journal des événements horodatés en UTC
    - Et la scrutation s'interrompt dès que la session atteint le statut terminal completed avec affichage du bouton « Voir les résultats »
  - État de chargement / attente :
    - Étant donné la session tout juste initiée
    - Quand les agents sont en phase d'initialisation
    - Alors les cartes indiquent l'état « EN ATTENTE » avec animation discrète
  - État vide :
    - Étant donné une session au démarrage sans événements produits
    - Quand le journal d'activité est instancié
    - Alors la mention « Initialisation du flux d'activité... » s'affiche
  - État d'erreur :
    - Étant donné une coupure prolongée de connectivité pendant la surveillance
    - Quand les requêtes de scrutation échouent de façon répétée
    - Alors la scrutation s'arrête et un bandeau propose le bouton « Réessayer la connexion » (DP-05)
  - État d'accès refusé :
    - Étant donné un opérateur non autorisé
    - Quand il tente d'accéder à la console
    - Alors l'accès est bloqué et l'opérateur est redirigé vers /cases

#### Story F4.4 : Commandes de contrôle de session et reprise sélective d'agent en incident
- En tant que : Enquêteur DFIR
- Je veux : Suspendre, reprendre ou annuler la session d'exécution, et relancer unitairement un agent tombé en échec
- Afin de : Conserver le contrôle opérationnel sur l'orchestration et rattraper un incident technique sans réexécuter toute la chaîne
- Dépendance contrat : bloquée par contrat : E5
- Paramètres d'architecture : aucun
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné une session d'exécution en cours
    - Quand l'analyste clique sur « Suspendre la session » ou « Reprendre »
    - Alors la commande POST /api/cases/:caseId/run/control est envoyée et l'interface répercute le changement d'état
    - Et le clic sur « Annuler la session » ouvre un dialogue de confirmation obligatoire avant exécution
    - Et si une carte d'agent passe à l'état failed, elle affiche le diagnostic d'incident et un bouton interactif « Réessayer cet agent » qui relance cet agent uniquement
  - État de chargement :
    - Étant donné une commande de contrôle ou de relance d'agent en cours d'envoi
    - Quand la requête transite
    - Alors le bouton sollicité affiche un indicateur de chargement
  - État vide :
    - Étant donné une session déjà terminée (completed ou canceled)
    - Quand la barre de commandes est restituée
    - Alors les boutons de suspension et d'annulation sont désactivés
  - État d'erreur :
    - Étant donné le rejet d'un ordre de contrôle par l'API
    - Quand une erreur 5xx survient
    - Alors une notification toast signale l'impossibilité d'exécuter l'action et propose de renouveler l'ordre
  - État d'accès refusé :
    - Étant donné un profil non habilité à piloter l'exécution
    - Quand il visualise la console
    - Alors les commandes de suspension, reprise, annulation et relance d'agent sont masquées

#### Story F4.5 : Cadre de navigation multi-vues des résultats et gestion des résultats partiels
- En tant que : Enquêteur DFIR
- Je veux : Naviguer entre les trois onglets (Chronologie, Artefacts, Hypothèses) sur /cases/:caseId/results et être prévenu si des résultats sont partiels
- Afin de : Disposer d'un espace d'analyse structuré et identifier immédiatement si des données manquent suite à l'échec d'un agent
- Dépendance contrat : bloquée par contrat : E7
- Paramètres d'architecture : à caler : C2 (délai maximal de réactivité au basculement d'onglet : à décider)
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné la fin de session des agents
    - Quand l'analyste accède à /cases/:caseId/results
    - Alors l'en-tête expose les trois onglets : Chronologie, Artefacts, Hypothèses
    - Et le basculement d'onglet met à jour la zone de contenu sans rechargement de page
    - Et si la session d'exécution a enregistré l'échec d'un ou plusieurs agents, un bandeau d'alerte permanent cyan (#01DBDC) avec libellé textuel explicite « RÉSULTATS PARTIELS : L'agent [Nom] a échoué. Certaines observations peuvent manquer. » est affiché
  - État de chargement :
    - Étant donné le changement d'onglet
    - Quand les données de la vue cible se chargent
    - Alors des squelettes adaptés à l'onglet sélectionné s'affichent
  - État vide :
    - Étant donné un dossier pour lequel aucun résultat n'a été produit
    - Quand la vue s'ouvre
    - Alors le message « Aucun résultat généré pour ce dossier » est affiché avec un bouton renvoyant vers le plan d'investigation
  - État d'erreur :
    - Étant donné une défaillance de chargement globale des données de résultats
    - Quand l'API renvoie un code 500
    - Alors un message d'erreur avec option de réessai est présenté dans la zone principale
  - État d'accès refusé :
    - Étant donné un utilisateur non autorisé sur le dossier
    - Quand il sollicite la route des résultats
    - Alors l'accès est rejeté et l'opérateur est redirigé vers /cases

#### Story F4.6 : Chronologie unifiée des faits techniques avec pagination serveur par blocs de 100
- En tant que : Enquêteur DFIR
- Je veux : Consulter la liste chronologique des événements techniques ordonnée en UTC, filtrer par type de source et période, avec une pagination serveur stricte par blocs de 100
- Afin de : Reconstituer l'enchaînement exact des faits sans saturation de la mémoire du navigateur sur les volumes massifs
- Dépendance contrat : bloquée par contrat : E7
- Paramètres d'architecture : aucun
- Décisions appliquées : DP-01 (chronologie en pagination serveur par blocs de 100 événements)
- Critères d'acceptation :
  - État nominal :
    - Étant donné l'onglet Chronologie sélectionné sur /cases/:caseId/results
    - Quand les événements sont récupérés depuis l'API
    - Alors la liste affiche exactement 100 événements par tranche de pagination serveur (DP-01)
    - Et chaque ligne mentionne la date/heure normalisée UTC, le résumé de l'observation et la source technique associée
    - Et la barre de filtres permet de restreindre par typologie de source (EVTX, logs, Prefetch, Registre, RAM) et intervalle de dates UTC
    - Et un sélecteur de page serveur permet de naviguer de tranche en tranche de 100 éléments avec maintien des filtres
  - État de chargement :
    - Étant donné un changement de page ou l'application d'un filtre temporel
    - Quand l'API traite la requête paginée
    - Alors des squelettes linéaires de chronologie s'affichent pendant la transition
  - État vide :
    - Étant donné des filtres temporels ou de source ne retournant aucun fait technique
    - Quand la liste filtrée est vide
    - Alors la mention « Aucun événement chronologique ne correspond aux critères sélectionnés » apparaît avec un bouton de réinitialisation des filtres
  - État d'erreur :
    - Étant donné un échec de récupération du flux chronologique
    - Quand le serveur renvoie une erreur
    - Alors un bloc d'alerte signale le dysfonctionnement avec commande de réactualisation
  - État d'accès refusé :
    - Étant donné une perte de privilèges sur le dossier
    - Quand la requête est émise
    - Alors l'accès est refusé et le tableau est masqué

#### Story F4.7 : Panneau latéral d'inspection de la source d'un événement forensique
- En tant que : Enquêteur DFIR
- Je veux : Cliquer sur la référence de source d'un événement chronologique pour ouvrir un tiroir latéral affichant l'extrait technique brut, l'offset et l'empreinte SHA-256
- Afin de : Vérifier l'ancrage probatoire irréfutable de chaque constatation technique
- Dépendance contrat : bloquée par contrat : E4
- Paramètres d'architecture : à caler : C2 (délai maximal de réactivité à l'ouverture du tiroir : à décider)
- Décisions appliquées : DP-04 (artefacts tronqués à 500 lignes ou 64 Ko, avec téléchargement direct)
- Critères d'acceptation :
  - État nominal :
    - Étant donné un analyste parcourant la chronologie unifiée
    - Quand il clique sur le lien de source d'un événement
    - Alors un tiroir latéral coulissant s'ouvre sans masquer la chronologie
    - Et le tiroir présente l'extrait brut de l'observation forensique, l'identifiant de la preuve source, l'offset ou chemin interne dans l'artefact, et le SHA-256 de la preuve
    - Et si l'extrait brut dépasse le seuil de 500 lignes ou 64 Ko, l'affichage est tronqué avec la mention « Extrait tronqué à 500 lignes / 64 Ko » et un bouton « Télécharger l'extrait complet » est proposé (DP-04)
    - Et un bouton de copie permet de copier l'extrait affiché dans le presse-papier
  - État de chargement :
    - Étant donné le clic sur une source technique
    - Quand les détails de l'observation sont demandés à l'API
    - Alors le tiroir s'ouvre avec un squelette de métadonnées et un bloc de texte en chargement
  - État vide :
    - Étant donné une observation ne disposant pas d'extrait textuel complémentaire
    - Quand le tiroir est affiché
    - Alors la mention « Aucun détail textuel supplémentaire pour cette observation » apparaît
  - État d'erreur :
    - Étant donné une impossibilité de récupérer l'extrait brut
    - Quand l'API renvoie une erreur 404 ou 500
    - Alors le tiroir affiche la mention « Données de source indisponibles » avec le motif technique retourné
  - État d'accès refusé :
    - Étant donné un accès refusé sur les preuves sources
    - Quand la requête est bloquée
    - Alors le tiroir affiche un message d'interdiction de consultation

#### Story F4.8 : Arbitrage qualitatif des findings en porte H2 et règle de blocage
- En tant que : Enquêteur DFIR
- Je veux : Arbitrer unitairement chaque finding pré-certifié (valider, rejeter avec motif, annoter) sur /cases/:caseId/review
- Afin de : Franchir la porte H2 et débloquer la génération du rapport final dès qu'au moins un finding est validé
- Dépendance contrat : bloquée par contrat : E6
- Paramètres d'architecture : aucun
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné l'écran de revue /cases/:caseId/review ouvert à la section Porte H2
    - Quand l'analyste consulte les constats formulés par l'Analyst et vérifiés par le Verifier
    - Alors chaque carte expose titre, typologie (fact, inference, hypothesis), sévérité, score de confiance et liens vers les observations sources
    - Et l'analyste peut cliquer sur « Valider », « Rejeter » (avec saisie obligatoire du motif de rejet) ou « Ajouter une annotation »
    - Et la décision est persistée via POST /api/cases/:caseId/findings/:id/decide avec horodatage UTC
    - Et le bouton « Accéder au rapport » reste strictement bloqué et grisé tant qu'aucun finding n'a été validé formellement par l'analyste
    - Et dès qu'un premier finding est validé, l'accès à la génération du rapport est immédiatement déverrouillé
  - État de chargement :
    - Étant donné l'enregistrement d'une décision d'arbitrage
    - Quand l'appel réseau est en vol
    - Alors les commandes de la carte de finding concernée sont désactivées avec indicateur de sauvegarde
  - État vide :
    - Étant donné une enquête n'ayant généré aucun finding
    - Quand la vue est affichée
    - Alors le message « Aucun finding à réviser pour ce dossier » s'affiche
  - État d'erreur :
    - Étant donné une tentative de rejet sans saisie du motif ou une défaillance API
    - Quand la validation est tentée
    - Alors le champ motif est signalé comme obligatoire
    - Et en cas d'erreur serveur, le motif et les annotations saisies sont conservés en mémoire sans perte (NFR-ERR-02)
  - État d'accès refusé :
    - Étant donné un profil non analyste
    - Quand il accède à la vue de revue
    - Alors les boutons d'arbitrage (valider, rejeter) sont masqués, la vue restant en lecture seule

#### Story F4.9 : Arbitrage de confidentialité et transmission externe en porte H3
- En tant que : Responsable Sécurité (CISO/RSSI) ou Enquêteur DFIR
- Je veux : Consulter la synthèse pseudonymisée par Microsoft Presidio et autoriser expressément l'envoi externe ou basculer en génération locale
- Afin de : Franchir la porte H3 en garantissant la confidentialité des données sensibles avant toute sollicitation d'un modèle externe
- Dépendance contrat : bloquée par contrat : E8
- Paramètres d'architecture : aucun
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné l'analyste sur la section Porte H3 de /cases/:caseId/review
    - Quand la prévisualisation de la synthèse pseudonymisée s'affiche
    - Alors l'écran détaille l'ensemble des entités caviardées par Microsoft Presidio (adresses IP, identifiants, noms d'hôtes)
    - Et une case à cocher explicite « J'autorise l'envoi de cette synthèse pseudonymisée » est requise pour activer le bouton « Valider et transmettre au modèle externe »
    - Et si l'opérateur refuse ou souhaite une autonomie stricte, l'action alternative « Générer le rapport en local » est accessible immédiatement
    - Et l'action validée enregistre l'accord ou le refus avec horodatage UTC et identité de l'analyste
  - État de chargement :
    - Étant donné la synthèse en cours de pseudonymisation côté serveur
    - Quand la vue est ouverte
    - Alors un écran d'attente animé signale le traitement Presidio en cours
  - État vide :
    - Étant donné un dossier sans findings validés en H2
    - Quand la section H3 est consultée
    - Alors la section affiche le message d'attente « Veuillez valider au moins un finding en porte H2 pour préparer la synthèse H3 »
  - État d'erreur / modèle externe indisponible :
    - Étant donné une panne de connectivité avec le modèle externe ou un incident sur le service Presidio
    - Quand l'API signale l'indisponibilité
    - Alors un message d'avertissement informe l'analyste et le bouton « Générer le rapport en local » est automatiquement mis en avant
  - État d'accès refusé :
    - Étant donné un utilisateur ne disposant pas du rôle requis pour autoriser une diffusion externe
    - Quand il consulte la section H3
    - Alors la case à cocher et le bouton de transmission externe sont désactivés avec mention explicite du rôle nécessaire

---

### Épic F5 : Rapport, états d'erreur globaux, accessibilité, parcours de bout en bout

- Objectif de l'épic : Finaliser l'Étape 5 du canevas en déclenchant la compilation du rapport d'incident scellé par le back-end et son téléchargement multi-formats (DP-03), déployer les gestionnaires d'erreurs et de résilience transverses avec prise en charge des statuts non répertoriés sans rupture d'arbre React, assurer l'audit et la conformité 100% WCAG 2.1 AA au clavier et non chromatique sous la palette stricte, et certifier l'ensemble du parcours nominal par un scénario Playwright de bout en bout en dix étapes.
- FR couvertes : FR-REP-01, FR-REP-02
- Dépendance au contrat back : Épic E8 (Rapports et journal d'audit), Épic E9 (Déploiement et démonstration)
- Critères de fin d'épic :
  1. L'écran /cases/:caseId/report permet de déclencher la compilation du rapport scellé à 100% par le back-end (DP-03) et prévisualise le livrable complet structuré en huit chapitres sur conteneur de lecture mist (#B7DFDF).
  2. L'historique des versions scellées restitue les empreintes SHA-256 et offre le téléchargement direct aux formats Markdown, PDF et JSON.
  3. Le composant transverse de résilience capture les statuts inconnus affichés sous forme « État inconnu (code_brut) » sans plantage de l'arbre React, et préserve les saisies utilisateur en mémoire en cas d'erreur 5xx.
  4. L'accessibilité WCAG 2.1 AA est validée : navigation intégrale au clavier avec anneau cyan (#01DBDC) de 2px, contrastes AA respectés sur les cinq couleurs strictes, signalement systématique par texte en majuscules associé à une icône lucide-react.
  5. La suite Playwright valide avec succès le parcours nominal en dix étapes sur stations Chromium, Gecko et WebKit.

#### Story F5.1 : Prévisualisation et déclenchement de la compilation serveur du rapport d'incident
- En tant que : Enquêteur DFIR ou Responsable Sécurité
- Je veux : Déclencher la compilation du rapport scellé par le back-end sur /cases/:caseId/report et visualiser le document structuré en huit chapitres
- Afin de : Disposer d'un livrable formel scellé, rigoureux et opposable sans compilation autonome côté front
- Dépendance contrat : bloquée par contrat : E8
- Paramètres d'architecture : aucun
- Décisions appliquées : DP-03 (rapports produits et scellés par le back-end ; le front ne compile rien), DP-05 (arrêt de l'interrogation en cas de coupure prolongée, avec bouton « Réessayer la connexion »)
- Critères d'acceptation :
  - État nominal :
    - Étant donné un dossier avec au moins un finding validé en porte H2 et arbitrage H3 consigné
    - Quand l'analyste clique sur « Compiler le rapport »
    - Alors une requête POST /api/cases/:caseId/report/generate est émise vers le back-end (DP-03)
    - Et la scrutation surveille la génération jusqu'à l'état validated
    - Et le rapport s'affiche dans un conteneur de lecture sur fond clair de papier mist (#B7DFDF) avec texte ink (#020C0C)
    - Et le document présente fidèlement les huit chapitres : résumé managérial, périmètre, méthodologie, chaîne des preuves, observations, findings validés en H2, chronologie et limites
  - État de chargement / en cours de génération :
    - Étant donné la compilation en cours côté serveur
    - Quand l'opération asynchrone s'exécute
    - Alors un écran animé avec la mention « Compilation et scellement du rapport en cours... » s'actualise par scrutation
  - État vide :
    - Étant donné l'accès à l'écran avant toute génération de rapport
    - Quand aucun rapport n'a encore été compilé
    - Alors un message descriptif invite l'analyste à lancer la compilation via le bouton principal
  - État d'erreur :
    - Étant donné un incident lors de la compilation par le back-end
    - Quand l'API renvoie un statut failed
    - Alors une alerte détaille le motif de l'incident et fournit le bouton « Réessayer la compilation »
    - Et en cas de coupure réseau prolongée, la scrutation s'arrête avec le bouton « Réessayer la connexion » (DP-05)
  - État d'accès refusé :
    - Étant donné une tentative d'accès à la compilation alors qu'aucun finding n'est validé en H2
    - Quand l'écran est sollicité
    - Alors la commande de compilation reste verrouillée avec l'indication « La validation d'au moins un finding en porte H2 est requise pour générer le rapport »

#### Story F5.2 : Historique des versions scellées et téléchargement direct multi-formats
- En tant que : Enquêteur DFIR ou Responsable Sécurité
- Je veux : Consulter l'historique des versions de rapports scellées avec leurs empreintes SHA-256 et télécharger directement les formats Markdown, PDF et JSON
- Afin de : Transmettre des livrables immuables aux équipes de direction ou aux autorités compétentes
- Dépendance contrat : bloquée par contrat : E8
- Paramètres d'architecture : aucun
- Décisions appliquées : DP-03 (rapports scellés et servis directement par le back-end)
- Critères d'acceptation :
  - État nominal :
    - Étant donné l'écran /cases/:caseId/report
    - Quand la section d'historique est consultée
    - Alors un tableau liste toutes les versions générées avec : numéro de version, horodatage UTC, auteur, statut de scellement et empreinte cryptographique SHA-256 complète avec bouton de copie
    - Et chaque ligne propose trois boutons de téléchargement direct pour les formats Markdown, PDF et JSON
    - Et le clic sur un bouton déclenche le téléchargement du fichier binaire ou textuel scellé directement servi par le back-end (DP-03)
  - État de chargement :
    - Étant donné la récupération de l'historique des versions
    - Quand les données transitent
    - Alors des squelettes de tableau s'affichent
  - État vide :
    - Étant donné un dossier ne disposant pas encore d'archives de rapports
    - Quand le tableau est instancié
    - Alors la mention « Aucune version archivée pour ce dossier » apparaît
  - État d'erreur :
    - Étant donné l'interruption d'un téléchargement ou un fichier introuvable côté serveur
    - Quand une erreur 404/500 survient sur le téléchargement
    - Alors une notification toast informe l'analyste de l'échec et invite à relancer l'export
  - État d'accès refusé :
    - Étant donné un utilisateur non autorisé à extraire des rapports sensibles
    - Quand il tente de télécharger un document
    - Alors l'accès au fichier est refusé avec le code HTTP 403

#### Story F5.3 : Résilience applicative, gestionnaire d'états d'erreur globaux et statuts inconnus
- En tant que : Analyste SOC ou Enquêteur DFIR
- Je veux : Que les statuts non répertoriés retournés par l'API s'affichent sous forme « État inconnu (code_brut) » sans planter l'arbre React et que mes formulaires restent préservés en cas d'erreur 5xx
- Afin de : Continuer mon travail d'investigation en environnement dégradé sans perte de données saisies
- Dépendance contrat : aucune
- Paramètres d'architecture : aucun
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné une réponse d'API contenant un statut imprévu ou nouveau (non documenté dans le contrat actuel)
    - Quand le composant d'affichage de statut traite la valeur
    - Alors l'interface affiche sans planter la mention « État inconnu (code_brut) » accompagnée d'une icône d'interrogation neutre
    - Et les actions dépendantes de ce statut sont désactivées par précaution (NFR-ERR-01)
    - Et le reste de l'écran demeure parfaitement consultable
  - État de chargement :
    - Étant donné la réévaluation de la résilience lors des requêtes
    - Quand l'intercepteur traite les réponses
    - Alors aucun délai perceptible n'est introduit dans le cycle de vie du rendu
  - État vide :
    - Étant donné une absence de données inattendue dans une réponse API
    - Quand le composant de vue déstructure l'objet
    - Alors des valeurs par défaut sécurisées préviennent toute exception de type référence nulle
  - État d'erreur :
    - Étant donné une panne de communication réseau ou une erreur HTTP 500 survenue lors de la soumission d'un formulaire (création de dossier, motif de rejet H1, annotation de finding H2)
    - Quand l'erreur est interceptée
    - Alors l'ensemble des textes saisis dans les champs reste intégralement préservé en mémoire dans le composant (NFR-ERR-02)
    - Et une notification toast claire signale l'anomalie avec bouton invitant à réessayer
  - État d'accès refusé :
    - Étant donné une erreur 403 transverse non gérée localement
    - Quand le gestionnaire global capture le code
    - Alors l'application affiche la bannière « Droits d'accès insuffisants » et réoriente proprement sans blocage

#### Story F5.4 : Audit et mise en conformité de l'accessibilité WCAG 2.1 AA et palette stricte
- En tant que : Opérateur en situation de handicap visuel ou moteur
- Je veux : Naviguer sur 100% des composants au clavier seul avec un anneau de focus cyan (#01DBDC) de 2px, bénéficier d'un signalement non chromatique et vérifier la conformité des contrastes
- Afin de : Utiliser la plateforme d'investigation de façon équitable, accessible et sans ambiguïté sur les données critiques
- Dépendance contrat : aucune
- Paramètres d'architecture : aucun
- Décisions appliquées : aucune
- Critères d'acceptation :
  - État nominal :
    - Étant donné un opérateur naviguant sur l'ensemble des écrans applicatifs
    - Quand il utilise la touche Tabulation et les touches Entrée ou Espace
    - Alors 100% des éléments interactifs (boutons, champs, onglets, tiroirs, cases à cocher) sont focalisables et actionnables sans souris (NFR-ACC-03)
    - Et un anneau de focus visuel cyan (#01DBDC) de 2 pixels de contour entoure nettement l'élément actif
    - Et 100% des badges de statut, alertes et sévérités associent simultanément un libellé textuel en lettres majuscules et une icône distincte lucide-react (NFR-ACC-02)
    - Et l'ensemble des contrastes de texte est strictement supérieur ou égal à 4.5:1 (mist sur ink à 13.80, teal sur ink à 6.09, ink sur mist à 13.80) sans aucune couleur hors palette stricte (NFR-ACC-01)
  - État de chargement :
    - Étant donné l'affichage de squelettes ou de jauges de chargement
    - Quand le focus atteint ces éléments
    - Alors les attributs ARIA aria-busy="true" et aria-live="polite" informent les technologies d'assistance
  - État vide :
    - Étant donné un état vide affiché dans un tableau ou un panneau
    - Quand le clavier parcourt la vue
    - Alors le bouton d'action principal de l'état vide reçoit le focus de manière logique
  - État d'erreur :
    - Étant donné un message d'erreur ou d'alerte affiché à l'écran
    - Quand l'anomalie se produit
    - Alors le composant est pourvu du rôle ARIA alert ou aria-live="assertive" permettant une restitution vocale immédiate
  - État d'accès refusé :
    - Étant donné un écran d'accès refusé
    - Quand l'utilisateur navigue
    - Alors le focus est automatiquement positionné sur le message explicatif et l'action de retour

#### Story F5.5 : Validation automatisée du parcours nominal E2E de bout en bout
- En tant que : Équipe de développement et QA
- Je veux : Exécuter la suite de tests Playwright automatisée déroulant les dix étapes du scénario nominal d'investigation sur Chromium, Firefox et WebKit
- Afin de : Certifier la chaîne fonctionnelle complète du front-end et garantir l'absence de régression avant la recette
- Dépendance contrat : bloquée par contrat : E9
- Paramètres d'architecture : à caler : C1 (seuil FCP : à décider), à caler : C2 (délai de réactivité aux interactions : à décider)
- Décisions appliquées : vérifie DP-01 à DP-06
- Critères d'acceptation :
  - État nominal :
    - Étant donné l'environnement de démonstration et d'intégration déployé
    - Quand la suite de tests E2E Playwright est exécutée
    - Alors les dix étapes s'enchaînent avec succès :
      1. Connexion sur /login avec conservation du jeton Bearer en mémoire vive
      2. Création d'un dossier via modale et navigation sur /cases/:caseId
      3. Dépôt de preuves avec jauges XHR sur /cases/:caseId/evidence
      4. Scrutation et atteinte de l'état intègre (completed) déverrouillant « Lancer l'analyse »
      5. Consultation et validation du plan d'action franchissant la porte H1 sur /cases/:caseId/plan
      6. Supervision des cartes d'agents sur /cases/:caseId/run jusqu'au statut completed
      7. Exploration des résultats sur /cases/:caseId/results avec pagination par 100 (DP-01) et inspection de source
      8. Validation formelle des findings en porte H2 sur /cases/:caseId/review
      9. Consentement de pseudonymisation Presidio en porte H3
      10. Compilation et téléchargement direct du rapport scellé sur /cases/:caseId/report (DP-03)
  - État de chargement :
    - Étant donné les transitions asynchrones entre chaque étape du scénario E2E
    - Quand les données sont attendues
    - Alors les assertions de test valident la présence des indicateurs de chargement avant l'affichage nominal
  - État vide :
    - Étant donné les contrôles d'états initiaux au fil des étapes
    - Quand les vues sont encore vierges
    - Alors le test valide la conformité des messages d'états vides avant la création de données
  - État d'erreur :
    - Étant donné des tests d'injection d'erreurs (rupture réseau simulée, rejet de validation)
    - Quand les anomalies surviennent
    - Alors le test vérifie la non-apparition de ruptures d'affichage et la bonne restitution des messages d'erreur
  - État d'accès refusé :
    - Étant donné un test d'accès direct sans jeton ou avec jeton invalide
    - Quand la navigation tente d'accéder aux routes protégées
    - Alors le test certifie la redirection systématique vers /login et le blocage complet des données confidentielles

---

## 5. Synthèse des Stories par Épic et Dépendances

| Épic | Nombre de stories | Stories | Dépendances aux contrats back-end |
|---|---|---|---|
| Épic F1 | 7 | F1.1, F1.2, F1.3, F1.4, F1.5, F1.6, F1.7 | E1 (F1.2, F1.3, F1.4, F1.5), E2 (F1.6, F1.7) |
| Épic F2 | 2 | F2.1, F2.2 | E2 (F2.1, F2.2) |
| Épic F3 | 3 | F3.1, F3.2, F3.3 | E3 (F3.1, F3.2, F3.3) |
| Épic F4 | 9 | F4.1, F4.2, F4.3, F4.4, F4.5, F4.6, F4.7, F4.8, F4.9 | E5 (F4.1, F4.2, F4.3, F4.4), E7 (F4.5, F4.6), E4 (F4.7), E6 (F4.8), E8 (F4.9) |
| Épic F5 | 5 | F5.1, F5.2, F5.3, F5.4, F5.5 | E8 (F5.1, F5.2), E9 (F5.5) |
| **Total** | **26** | **F1.1 à F5.5** | **E1, E2, E3, E4, E5, E6, E7, E8, E9** |

---

*Document d'épics et de récits utilisateurs front-end finalisé pour le périmètre MVP d'IRYX. Statut : validé. Validé formellement par le Team Lead et l'utilisateur.*
