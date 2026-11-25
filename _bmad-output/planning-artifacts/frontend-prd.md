---
title: "Document des Exigences Produit (PRD) : Front-End IRYX"
version: "1.0-mvp"
status: "validé"
created: "2026-11-25"
updated: "2026-11-25"
author: "BMad Master Facilitator (Agent Analyst & PM)"
project: "IRYX"
scope: "Front-End MVP"
---

# Document des Exigences Produit (PRD) : Front-End IRYX (MVP)

---

## 1. Vision du Produit et Contexte

### 1.1 Contexte opérationnel
IRYX est une plateforme d'investigation numérique (DFIR) et d'analyse de fraudes financières assistée par une constellation d'agents d'intelligence artificielle spécialisés et supervisée de manière continue par l'humain.

L'interface front-end constitue l'espace de travail unifié de l'enquêteur. Elle offre un environnement d'investigation rigoureux, ergonomique et résilient, permettant de piloter l'ingestion de preuves volumineuses (journaux d'événements Windows EVTX, ruches de registre, Prefetch, images mémoire RAM), d'arbitrer les stratégies forensiques proposées par les agents, d'inspecter les observations techniques sans risque d'hallucination, et d'éditer des rapports d'incident certifiés et scellés.

### 1.2 Règle d'or de conception
Le front-end reflète fidèlement l'état et la logique du back-end sans jamais s'y substituer. Aucune règle métier, calcul de conformité légale ou déduction d'état ne s'exécute de façon autonome dans le navigateur. L'interface matérialise de façon inviolable les trois portes de contrôle humain (gates H1, H2, H3), garantissant qu'aucune action d'outil ni aucune diffusion externe de données sensibles ne puisse survenir sans l'approbation explicite de l'analyste.

---

## 2. Personas Utilisateurs

Le front-end répond aux exigences opérationnelles de trois personas clés :

### 2.1 Persona 1 : Analyste SOC (Niveau 1 / Niveau 2)
- **Rôle** : Qualification des alertes de sécurité, triage initial des incidents et détection de fraudes.
- **Besoins dans l'interface** : Téléversement intuitif de preuves hétérogènes, visibilité instantanée sur la conformité des empreintes SHA-256 et l'état d'ingestion, navigation rapide sans saturation cognitive.
- **Contraintes** : Délais de traitement restreints par les SLA, gestion de crises opérationnelles sous stress.

### 2.2 Persona 2 : Enquêteur numérique / Spécialiste DFIR
- **Rôle** : Conduite d'investigations techniques approfondies, analyse de causes racines, constitution de dossiers opposables.
- **Besoins dans l'interface** : Accès direct et transparent aux sources brutes (tiroir d'inspection d'observation, empreintes cryptographiques complètes, horodatages UTC précis), contrôle granulaire des étapes d'outils en porte H1, arbitrage rigoureux des constats en porte H2.
- **Contraintes** : Chaîne de possession intangible, rejet formel des erreurs masquées ou des interprétations non vérifiables.

### 2.3 Persona 3 : Responsable Sécurité (CISO / RSSI)
- **Rôle** : Supervision globale de la posture de défense, arbitrage sur le partage externe de données, diffusion des conclusions d'enquête.
- **Besoins dans l'interface** : Tableau de bord synthétique du dossier, contrôle des synthèses pseudonymisées avant transmission en porte H3, consultation et export scellé des rapports d'incident.
- **Contraintes** : Conformité réglementaire stricte sur la confidentialité des données et souveraineté opérationnelle.

---

## 3. Périmètre Fonctionnel du Front-End (MVP)

Le périmètre du MVP couvre dix écrans et vues spécialisées articulés autour de la structure séquentielle en cinq étapes d'un dossier d'enquête :
1. Authentification sécurisée de l'opérateur (`/login`).
2. Liste paginée et création des dossiers d'investigation (`/cases`).
3. Étape 1 : Tableau de bord de contexte et métadonnées du dossier (`/cases/:caseId`).
4. Étape 2 : Registre d'acquisition, téléversement de preuves et scellement SHA-256 (`/cases/:caseId/evidence`).
5. Étape 2 : Panneau latéral d'inspection détaillée d'une preuve (`/cases/:caseId/evidence/:evidenceId`).
6. Étape 3 : Plan d'investigation forensique et validation formelle de la porte H1 (`/cases/:caseId/plan`).
7. Étape 3 : Console de supervision temps réel des agents et contrôle de session (`/cases/:caseId/run`).
8. Étape 4 : Espace d'exploration des résultats en trois volets : Chronologie unifiée, Artefacts, Hypothèses (`/cases/:caseId/results`).
9. Étape 5 : Revue qualitative des findings en porte H2 et arbitrage de confidentialité en porte H3 (`/cases/:caseId/review`).
10. Étape 5 : Compilation, historique et téléchargement scellé des rapports d'incident (`/cases/:caseId/report`).

---

## 4. Exigences Fonctionnelles (Functional Requirements)

### 4.1 Authentification et Gestion de Session (Conformité ADR-0011)

#### FR-AUTH-01 : Connexion utilisateur
- **Écran associé** : `/login`
- **Description** : L'analyste saisit ses identifiants (adresse électronique et mot de passe). La soumission appelle l'endpoint d'authentification de l'API. En cas de succès, le jeton d'accès Bearer est réceptionné pour une durée de validité de 15 minutes et stocké exclusivement en mémoire vive volatile de l'application (aucun stockage dans localStorage ni sessionStorage). Un jeton de renouvellement d'une durée de validité de 7 jours est positionné sous forme de cookie httpOnly doté des attributs Secure et SameSite=Strict, limité au chemin `/api/auth/refresh` (décisions D1 et D3). L'analyste est automatiquement redirigé vers l'écran `/cases` (ou la route cible initialement demandée).
- **États obligatoires** :
  - *État de chargement* : Désactivation des champs de formulaire et indicateur de progression sur le bouton de soumission.
  - *État vide* : Formulaire de connexion initial prêt à la saisie.
  - *État d'erreur* : Message d'erreur unique et non discriminant « Identifiants incorrects » ; message d'erreur réseau en cas d'inaccessibilité de l'API.
  - *État nominal* : Redirection transparente vers la page demandée.

#### FR-AUTH-02 : Transmission sécurisée des requêtes protégées
- **Écran associé** : Toutes les routes sous `/cases/*`
- **Description** : Pour toute requête adressée aux ressources protégées de l'API, le client réseau intercepte l'appel et injecte le jeton d'accès actif dans l'en-tête HTTP standard `Authorization: Bearer <token>`. Aucun jeton d'accès n'est conservé dans le stockage persistant du navigateur (aucun enregistrement dans localStorage ni sessionStorage, aucun cookie pour les requêtes métier).
- **État attendu** : Transmission transparente sans altération de la charge utile métier.

#### FR-AUTH-03 : Détection d'expiration du jeton d'accès
- **Écran associé** : Transverse sur toutes les routes protégées
- **Description** : Lorsque l'API renvoie une réponse HTTP 401 sur un appel métier en raison de l'expiration du jeton d'accès après ses 15 minutes de validité (décision D3), le client d'interception réseau capture l'erreur sans interrompre l'affichage utilisateur ni afficher de message d'échec prématuré.
- **État attendu** : Suspension temporaire des requêtes sortantes dans une file d'attente en attente de renouvellement de session.

#### FR-AUTH-04 : Renouvellement silencieux de la session (modèle sans état D6)
- **Écran associé** : Transverse en tâche de fond
- **Description** : Dès détection d'une réponse 401 sur le jeton d'accès, le client réseau émet une requête asynchrone POST vers l'endpoint `/api/auth/refresh`. Le cookie httpOnly de renouvellement est transmis automatiquement par le navigateur, sous protection anti-CSRF par vérification de l'en-tête d'origine (`Origin` / `Sec-Fetch-Site`). Conformément au modèle sans état simple (décision D6), le serveur vérifie la validité cryptographique de la signature du refresh token (durée 7 jours) sans consultation de table en base de données et sans rotation du refresh token : le même refresh token reste valide durant ses 7 jours. Le serveur retourne un nouvel access token de 15 minutes, rechargé immédiatement en mémoire vive volatile (sans persistance dans localStorage ni sessionStorage). Les requêtes suspendues sont immédiatement rejouées avec le nouveau jeton d'accès.
- **État attendu** : Continuité de session fluide et totalement transparente pour l'utilisateur sans rechargement de page.

#### FR-AUTH-05 : Gestion de l'échec de renouvellement et expiration de session
- **Écran associé** : Transverse vers `/login`
- **Description** : Si la tentative de renouvellement échoue (réponse HTTP 401 sur `/api/auth/refresh` consécutive à l'expiration des 7 jours du refresh token ou à une signature invalide, conformément à D6), le client purge immédiatement le jeton d'accès de la mémoire vive (sans laisser de traces dans localStorage ni sessionStorage), interrompt les traitements en cours et redirige l'analyste vers `/login` avec la notification « Session expirée. Veuillez vous reconnecter. »
- **État attendu** : Redirection sécurisée vers `/login` avec mémorisation de l'URL cible courante pour retour après ré-authentification.

#### FR-AUTH-06 : Déconnexion explicite sans révocation serveur (modèle D6)
- **Écran associé** : Barre supérieure transverse (toutes les routes)
- **Description** : L'analyste clique sur l'action « Se déconnecter ». L'API ordonne la suppression du cookie httpOnly de renouvellement côté navigateur. Conformément aux risques acceptés du modèle sans état simple (décision D6), la déconnexion n'effectue aucune révocation du jeton côté serveur (absence de table de révocation en base). Le client vide intégralement la mémoire vive applicative (aucun résidu dans localStorage ni sessionStorage), réinitialise le cache de données et redirige immédiatement l'analyste vers `/login`.
- **État attendu** : Suppression du cookie client, purge de la mémoire et réorientation vers `/login`.

---

### 4.2 Gestion des Dossiers d'Investigation

#### FR-CASES-01 : Consultation paginée et recherche des dossiers
- **Écran associé** : `/cases`
- **Description** : L'interface affiche la liste ordonnée des dossiers de l'organisation sous forme de tableau paginé côté serveur (titre, statut global, date de détection, nombre de preuves scellées). Un champ de recherche textuelle permet de filtrer dynamiquement par titre.
- **États obligatoires** :
  - *État de chargement* : Lignes de squelettes animées dans le tableau.
  - *État vide* : Affichage du message « Aucun dossier d'investigation enregistré. Créez votre premier dossier. » accompagné d'un bouton d'action principal.
  - *État d'erreur* : Notification d'échec de récupération avec bouton « Réessayer ».
  - *État d'accès refusé* : Redirection automatique vers `/login` si non authentifié.
  - *État nominal* : Tableau paginé interactif avec sélection d'un dossier par clic de ligne.

#### FR-CASES-02 : Création d'un nouveau dossier d'investigation
- **Écran associé** : `/cases` (fenêtre modale)
- **Description** : L'analyste clique sur « Nouveau dossier » pour ouvrir une modale de saisie comprenant : titre de l'affaire, description factuelle, date/heure d'incident, typologie de crise, systèmes affectés. La validation côté client repose sur un schéma Zod aligné sur les règles de l'API. La soumission crée le dossier et redirige l'utilisateur vers son contexte.
- **États obligatoires** :
  - *État vide / saisie* : Champs prêts à l'enregistrement avec valeurs par défaut sur les dates.
  - *État de chargement* : Bouton de validation désactivé avec indicateur de création en cours.
  - *État d'erreur de validation* : Mise en évidence des champs invalides avec message d'aide explicite.
  - *État nominal* : Fermeture de la modale, notification toast de succès et navigation immédiate vers `/cases/:caseId`.

---

### 4.3 Contexte du Dossier (Étape 1 du canevas)

#### FR-CTX-01 : Consultation et modification du contexte
- **Écran associé** : `/cases/:caseId`
- **Description** : L'écran expose les informations administratives et techniques de l'affaire (titre, description, date de création, horodatage de dernière activité, liste en lecture seule des membres autorisés). Les analystes titulaires peuvent modifier le titre et la description via un mode d'édition en ligne.
- **États obligatoires** :
  - *État de chargement* : Blocs de substitution animés sur la fiche d'informations.
  - *État vide* : Mentions textuelles par défaut pour les champs optionnels non renseignés.
  - *État d'erreur* : Message d'impossibilité de charger le dossier avec bouton d'actualisation.
  - *État d'accès refusé* : Blocage complet de la vue et redirection vers `/cases` avec notification « Vous n'avez pas accès à ce dossier ».
  - *État nominal* : Fiche d'informations complète et éditable selon les droits de l'opérateur.

#### FR-CTX-02 : Évolution du statut global du dossier
- **Écran associé** : `/cases/:caseId`
- **Description** : Un sélecteur contrôlé permet à l'analyste de modifier le statut d'avancement de l'enquête parmi les valeurs valides du modèle : `open`, `in_progress`, `review`, `closed`. La mise à jour est immédiatement persistée par l'API.
- **État attendu** : Mise à jour instantanée du badge d'état dans l'en-tête et synchronisation de la barre latérale.

---

### 4.4 Acquisition et Registre des Preuves (Étape 2 du canevas)

#### FR-EVI-01 : Dépôt et téléversement de preuves avec progression
- **Écran associé** : `/cases/:caseId/evidence`
- **Description** : L'opérateur peut déposer par glisser-déposer ou sélection un ou plusieurs fichiers de preuves brutes (formats supportés : journaux EVTX, fichiers de logs textuels, ruches de registre Windows, fichiers Prefetch, captures mémoire vive RAM). L'envoi s'effectue via un module XMLHttpRequest dédié mesurant précisément la progression en pourcentage de chaque fichier.
- **États obligatoires** :
  - *État vide* : Zone de dépôt mise en avant avec rappel des formats et de la taille maximale autorisée.
  - *État en cours de transfert* : Barre de progression individuelle par fichier avec affichage du pourcentage et bouton d'annulation de téléversement.
  - *État refusé* : Rejet immédiat avec message descriptif si le format n'est pas reconnu ou si la taille dépasse le plafond configuré (aucune entrée créée).
  - *État nominal* : Fichiers téléversés basculant automatiquement dans le registre des preuves pour traitement d'ingestion.

#### FR-EVI-02 : Inventaire des preuves et suivi d'ingestion
- **Écran associé** : `/cases/:caseId/evidence`
- **Description** : Le tableau récapitule l'ensemble des preuves rattachées au dossier : nom d'origine, format détecté, volume en octets, empreinte SHA-256 tronquée, statut d'ingestion (`pending`, `processing`, `completed`, `failed`), horodatage UTC d'import et identité de l'opérateur. Les états non terminaux font l'objet d'une scrutation régulière (polling).
- **Règle d'activation de l'analyse** : Le bouton « Lancer l'analyse » est actif uniquement si au moins une preuve est à l'état `completed` (intègre). Si aucune preuve n'est intègre, le bouton reste grisé avec un message explicatif au survol.
- **États obligatoires** :
  - *État de chargement* : Indicateur de synchronisation de la liste.
  - *État vide* : Mention « Aucune preuve déposée pour ce dossier ».
  - *État d'échec d'ingestion* : Ligne signalée en alerte visuelle avec libellé « ÉCHEC », icône dédiée et lien d'accès au message d'erreur.
  - *État d'altération d'intégrité* : Si l'empreinte recalculée diverge, la preuve est marquée « NON INTÈGRE » et exclue de toute analyse.
  - *État nominal* : Registre synchronisé avec empreinte tronquée munie d'un bouton de copie dans le presse-papier.

#### FR-EVI-03 : Panneau d'inspection détaillée d'une preuve
- **Écran associé** : `/cases/:caseId/evidence/:evidenceId`
- **Description** : Un panneau latéral coulissant s'ouvre au clic sur une ligne de preuve. Il présente l'empreinte SHA-256 intégrale en typographie à chasse fixe, les métadonnées forensiques extraites, l'historique complet des exécutions d'ingestion et le décompte des observations générées.
- **États obligatoires** :
  - *État de chargement* : Squelettes de métadonnées en cours de chargement.
  - *État vide* : Mention « Aucune observation extraite » pour une preuve valide sans artefacts découverts.
  - *État d'erreur* : Notification d'échec de chargement des métadonnées détaillées.
  - *État nominal* : Affichage complet avec bouton de fermeture du panneau et copie intégrale d'empreinte.

---

### 4.5 Planification Forensique et Porte H1 (Étape 3 du canevas)

#### FR-PLAN-01 : Consultation du plan proposé par le Planner
- **Écran associé** : `/cases/:caseId/plan`
- **Description** : L'écran expose la séquence ordonnée d'étapes techniques d'investigation élaborée par l'agent Planner. Chaque étape détaille : le numéro d'ordre, l'objectif d'analyse, l'agent assigné, l'outil forensique requis (ex. analyseur EVTX, regipy, Volatility 3) et les preuves ciblées.
- **États obligatoires** :
  - *État en cours de planification* : Écran d'attente animé avec message « Élaboration du plan par le Planner en cours... » actualisé par scrutation régulière.
  - *État vide* : Notification « Aucun outil forensique applicable aux preuves disponibles » avec bouton de retour vers l'étape des preuves.
  - *État d'erreur* : Incident de planification avec affichage de la cause et bouton de réessai.
  - *État nominal* : Plan d'action détaillé prêt pour arbitrage par l'analyste.

#### FR-PLAN-02 : Arbitrage et validation formelle de la porte H1
- **Écran associé** : `/cases/:caseId/plan`
- **Description** : L'analyste examine les étapes proposées. Avant validation, il peut supprimer unitairement une étape jugée superflue. Il peut refuser le plan avec saisie d'un motif obligatoire (ce qui relance le Planner). La validation globale franchit formellement la porte H1 : le plan devient en lecture seule immuable, scellé avec l'horodatage UTC et l'identifiant de l'analyste, et déclenche la session d'exécution.
- **États obligatoires** :
  - *État d'accès refusé* : Pour les profils en consultation seule (non analystes), les actions de validation ou suppression sont masquées.
  - *État plan validé* : Affichage scellé en lecture seule avec mention « Plan validé par [Analyste] le [Date UTC] » et lien d'accès direct vers la console d'exécution.

---

### 4.6 Console d'Exécution des Agents (Étape 3 du canevas)

#### FR-RUN-01 : Supervision temps réel de l'orchestration des agents
- **Écran associé** : `/cases/:caseId/run`
- **Description** : L'interface présente une vue synoptique composée de cartes dédiées pour chaque agent de la chaîne (Planner, Executor, Analyst, Verifier, Corrélateur, Rapporteur). Chaque carte indique le statut dynamique (`pending`, `active`, `completed`, `failed`), la jauge d'avancement et le dernier message d'action. Un flux d'activité global retranscrit les événements horodatés en UTC. L'actualisation s'opère par scrutation périodique et s'interrompt dès l'atteinte d'un statut terminal.
- **États obligatoires** :
  - *État initial / attente* : Cartes en attente avec mention de la phase courante.
  - *État en cours* : Animation des cartes actives et défilement du journal d'activité.
  - *État terminé* : Notification de fin de traitement et mise en avant du bouton « Voir les résultats ».

#### FR-RUN-02 : Contrôle de session et reprise sur incident d'agent
- **Écran associé** : `/cases/:caseId/run`
- **Description** : L'analyste dispose d'actions de contrôle pour suspendre temporairement la session (mise en pause), la reprendre ou l'annuler définitivement (avec dialogue de confirmation obligatoire). En cas d'incident sur un agent spécifique, sa carte bascule en état d'échec avec affichage du diagnostic technique et d'un bouton « Réessayer cet agent », permettant de relancer l'agent sans interrompre le travail des autres composants.
- **État attendu** : Réactivité immédiate des commandes de contrôle et isolation des défaillances unitaires.

---

### 4.7 Exploration des Résultats d'Analyse (Étape 4 du canevas)

#### FR-RES-01 : Navigation multi-vues des résultats
- **Écran associé** : `/cases/:caseId/results`
- **Description** : L'écran structure les éléments probatoires et analytiques en trois onglets distincts : Chronologie, Artefacts et Hypothèses.
- **États obligatoires** :
  - *État de chargement* : Squelettes de données sur les onglets.
  - *État vide* : Message informatif « Aucun résultat généré pour ce dossier » avec invitation à consulter le plan.
  - *État de résultats partiels* : Bannière d'avertissement permanente indiquant la liste des agents dont l'échec a pu tronquer les données restituées.
  - *État nominal* : Espace de consultation complet et filtrable.

#### FR-RES-02 : Chronologie unifiée des faits techniques
- **Écran associé** : `/cases/:caseId/results` (onglet Chronologie)
- **Description** : Restitution d'une liste séquentielle linéaire ordonnée selon l'horodatage UTC extrait des artefacts. L'analyste peut filtrer les événements par type de source (journaux EVTX, exécutions Prefetch, ruches de registre, mémoire RAM) et par intervalle temporel. Chaque ligne affiche la date UTC normalisée, le résumé de l'observation et la référence de la source.
- **État attendu** : Défilement fluide des événements avec maintien des filtres temporels.

#### FR-RES-03 : Panneau latéral d'inspection de la source
- **Écran associé** : `/cases/:caseId/results`
- **Description** : Le clic sur la source d'un événement chronologique ouvre un tiroir latéral affichant l'extrait technique brut de l'observation, l'identifiant de la preuve d'origine, le chemin ou l'offset interne dans l'artefact, et l'empreinte SHA-256 de la preuve garante de la chaîne de traçabilité.
- **État attendu** : Lecture seule stricte avec fonction de copie de l'extrait brut.

---

### 4.8 Arbitrage des Findings (H2) et Confidentialité (H3) (Étape 5 du canevas)

#### FR-REV-01 : Arbitrage qualitatif des findings en porte H2
- **Écran associé** : `/cases/:caseId/review`
- **Description** : L'écran expose la liste des findings formulés par l'agent Analyst et pré-certifiés par le composant déterministe Verifier. Pour chaque constat, l'analyste consulte le titre, la typologie (`fact`, `inference`, `hypothesis`), la sévérité, le score de confiance et les observations sources liées. L'analyste enregistre sa décision unitaire : valider (pour intégration au rapport), rejeter (avec motif) ou annoter.
- **Règle de blocage** : Le déclenchement de la génération du rapport final demeure strictement désactivé tant qu'au moins un finding n'a pas été validé formellement par l'analyste.
- **États obligatoires** :
  - *État en attente* : Findings proposés disponibles pour arbitrage.
  - *État vide* : Message « Aucun finding à réviser ».
  - *État nominal* : Enregistrement synchrone de chaque décision avec horodatage d'arbitrage.

#### FR-REV-02 : Arbitrage de confidentialité et transmission externe en porte H3
- **Écran associé** : `/cases/:caseId/review`
- **Description** : L'analyste accède à la section dédiée à la transmission externe. L'interface affiche la synthèse d'enquête après pseudonymisation par Microsoft Presidio, avec inventaire détaillé des entités caviardées (adresses IP, identifiants de comptes, noms d'hôtes). L'analyste doit cocher obligatoirement la mention « J'autorise l'envoi de cette synthèse pseudonymisée » pour débloquer la génération via le modèle externe. Si l'autorisation est refusée ou en cas de défaillance réseau, l'interface propose la génération locale intégrale du rapport.
- **États obligatoires** :
  - *État modèle externe indisponible* : Message d'avertissement et mise en avant immédiate de la commande « Générer le rapport en local ».
  - *État nominal* : Contrôle absolu de l'analyste sur la diffusion externe.

---

### 4.9 Restitution et Archivage des Rapports (Étape 5 du canevas)

#### FR-REP-01 : Compilation et visualisation du rapport d'enquête
- **Écran associé** : `/cases/:caseId/report`
- **Description** : L'analyste déclenche la compilation du rapport d'incident. L'interface prévisualise le document structuré en huit chapitres : résumé managérial, périmètre de l'enquête, méthodologie et outillage, chaîne des preuves et empreintes, observations techniques, findings validés en H2, chronologie des événements et limites d'investigation.
- **États obligatoires** :
  - *État en cours de génération* : Écran d'attente animé suivi par scrutation régulière.
  - *État d'échec de compilation* : Notification explicite avec option « Réessayer la génération ».
  - *État nominal* : Document complet affiché dans le conteneur de lecture sur fond clair de papier (`mist`).

#### FR-REP-02 : Historique des versions et export scellé
- **Écran associé** : `/cases/:caseId/report`
- **Description** : L'écran maintient un tableau historique de l'ensemble des versions de rapports générées pour le dossier (horodatage UTC, auteur, format, empreinte cryptographique SHA-256 du document compilé). Des actions de téléchargement direct permettent d'extraire les archives aux formats Markdown, PDF et JSON.
- **État attendu** : Téléchargement instantané de fichiers scellés prêts pour communication juridique ou réglementaire.

---

## 5. Exigences Non Fonctionnelles (Non-Functional Requirements)

### 5.1 Accessibilité visuelle et Ergonomie cognitive (Conformité WCAG 2.1 AA - Décision D5)
- **NFR-ACC-01 (Conformité des contrastes de couleur - WCAG 2.1 AA)** : 100% des textes affichés doivent être strictement conformes au niveau WCAG 2.1 AA. Le texte principal sur fond sombre (paire `mist` `#B7DFDF` sur fond `ink` `#020C0C`) et le texte secondaire (paire `teal` `#019F9E` sur fond `ink` `#020C0C`) respectent les exigences de contraste minimales du niveau AA (ratio supérieur ou égal à 4.5:1 pour le texte normal). Aucune exigence de niveau AAA n'est requise (décision D5). Le texte inversé sur fond papier (`ink` `#020C0C` sur fond `mist` `#B7DFDF`) satisfait également les seuils AA.
- **NFR-ACC-02 (Signalement non chromatique des sévérités)** : 100% des indicateurs de sévérité, statuts critiques et états d'échec doivent associer un libellé textuel explicite en lettres majuscules et une icône distincte issue de la bibliothèque lucide-react. Aucune information de criticité ne doit être transmise par la couleur seule.
- **NFR-ACC-03 (Navigation intégrale au clavier)** : 100% des composants interactifs du parcours principal (boutons, champs, onglets, tiroirs, cases à cocher) doivent être focalisables et actionnables au clavier seul via la touche Tabulation et la touche Entrée/Espace, avec un anneau de focus visuel cyan (`#01DBDC`) de 2 pixels de contour.

### 5.2 Performance d'Affichage et Réactivité
- **NFR-PERF-01 (Délai d'affichage initial - First Contentful Paint)** : Le délai d'affichage du premier contenu significatif (FCP) sur les écrans principaux est : à définir (mesuré lors des tests de performance).
- **NFR-PERF-02 (Délai de réactivité aux interactions internes)** : Le temps de réponse de l'interface lors d'un basculement d'onglet, de l'ouverture d'un panneau latéral ou du filtrage temporel de la chronologie est : à définir.
- **NFR-PERF-03 (Cadence et arrêt de la scrutation réseau)** : L'intervalle de scrutation périodique (polling) sur les états asynchrones longs (ingestion, agents, compilation) et le délai d'arrêt automatique dès l'atteinte d'un statut terminal ou changement de vue sont : à définir.

### 5.3 Compatibilité Navigateurs et Résolution Matérielle
- **NFR-COMPAT-01 (Support multi-navigateurs)** : L'application doit s'exécuter sans régression fonctionnelle ni divergence graphique sur les versions stables actuelles des moteurs Chromium (Google Chrome, Microsoft Edge version >= 120), Gecko (Mozilla Firefox version >= 120) et WebKit (Apple Safari version >= 17).
- **NFR-RESP-01 (Résolution d'écran minimale)** : L'interface est conçue pour des stations de travail bureautiques d'une résolution horizontale minimale de 1280 pixels et verticale minimale de 720 pixels. Aucun défilement horizontal de page ne doit apparaître à cette résolution.

### 5.4 Résilience et Gestion des Anomalies
- **NFR-ERR-01 (Résilience face aux statuts inconnus)** : 100% des statuts non répertoriés retournés par l'API doivent être affichés sous la forme « État inconnu (code_brut) » sans provoquer de plantage d'arbre React (déclenchement de limite d'erreur) ni empêcher la consultation des autres blocs de l'écran.
- **NFR-ERR-02 (Préservation des saisies sur panne réseau)** : En cas de coupure de communication réseau ou d'erreur serveur HTTP 5xx, l'ensemble des textes en cours de saisie dans les formulaires actifs (création de dossier, motifs de rejet, annotations de findings) doit être conservé en mémoire locale sans perte de données.

---

## 6. Contraintes Techniques et Cadre de Réalisation

1. **Palette stricte à cinq couleurs** :
   L'ensemble des composants, thèmes Tailwind et feuilles de styles doit utiliser exclusivement les cinq couleurs validées :
   - `#020C0C` (ink) : couleur de base et fond de page
   - `#19595A` (deep) : bordures, séparateurs et éléments de structure
   - `#019F9E` (teal) : textes secondaires et statuts neutres
   - `#01DBDC` (cyan) : actions primaires, focus actif et alertes élevées
   - `#B7DFDF` (mist) : texte principal et fond papier de rapport
   Tout usage de blanc pur, noir pur, rouge, vert, orange ou jaune est formellement prohibé.
2. **Langue française unique** :
   100% des libellés d'interface, messages de retour système, codes d'erreur affichés et documentations associées sont rédigés en langue française. Aucune bibliothèque d'internationalisation n'est incorporée au MVP.
3. **Architecture logicielle sans état côté client** :
   Le front-end n'embarque aucun magasin global métier persistant (pas de Redux ou Zustand pour les données d'investigation). L'état serveur est géré exclusivement via TanStack Query.
4. **Zéro code dans les livrables de cadrage** :
   Le présent document ne contient aucun extrait de code informatique, script ou instruction de programmation.

---

## 7. Hypothèses Structurantes

1. Le back-end exposera une API conforme aux standards REST et documentée par une spécification OpenAPI version 3.x respectant fidèlement le modèle de données de `docs/03-modele-de-donnees.md`.
2. L'infrastructure d'hébergement garantira la transmission des cookies `httpOnly` dans un environnement sécurisé (HTTPS avec `SameSite=Strict`), le front-end et l'API partageant le même domaine de premier niveau ou étant unifiés sous un reverse-proxy commun.
3. Les outils forensiques exécutés au sein de la Gateway produiront des observations pourvues d'horodatages au format UTC normalisé (ISO 8601).
4. Le service de pseudonymisation basé sur Microsoft Presidio (décision D-19) sera opérationnel et joignable côté back-end avant toute exécution de la porte H3.

---

## 8. Risques Acceptés et Limites Opérationnelles

Conformément à l'ADR-0011 et aux décisions d'architecture validées pour le MVP, les risques suivants sont formellement acceptés :

1. **Déconnexion sans révocation côté serveur (ADR-0011)** :
   L'action de déconnexion supprime le cookie de renouvellement côté navigateur de l'opérateur mais n'invalide pas la signature du jeton côté serveur (architecture sans état simple selon D6, sans table d'état ni liste de révocation en base de données). Par conséquent, un refresh token qui aurait été copié ou intercepté avant la déconnexion reste cryptographiquement valide auprès de l'API jusqu'à l'expiration de son délai de 7 jours. Ce risque accepté est atténué par les attributs stricts du cookie (httpOnly, Secure, SameSite=Strict), la restriction de chemin au seul endpoint `/api/auth/refresh`, le contrôle obligatoire de l'en-tête d'origine anti-CSRF, et la durée d'exposition très courte de l'access token (15 minutes).
2. **Absence de rotation unitaire du refresh token (ADR-0011)** :
   Le même refresh token de 7 jours est réutilisé à chaque renouvellement silencieux sans renouvellement de signature, simplifiant les échanges réseau sans écriture en base.
3. **Absence de détection de réutilisation (ADR-0011)** :
   L'absence de persistance d'état côté serveur ne permet pas de détecter le rejeu simultané d'un même refresh token depuis des postes différents.

---

## 9. Questions Ouvertes Restantes (Non Tranchées)

Conformément aux directives méthodologiques, les questions suivantes restent ouvertes et ne sont pas tranchées unilatéralement :

1. **Intégration d'un écran dédié pour le journal d'audit immuable (`AuditEvent`)** : La table d'audit existe côté back-end. Doit-on introduire un écran de consultation dédié dans le front-end pour la démonstration finale, ou cet affichage doit-il être strictement reporté en phase post-MVP ?
2. **Politique de limitation volumétrique et d'affichage de la chronologie** : Lorsque le volume cumulé d'événements extraits d'une image mémoire ou de multiples journaux EVTX dépasse plusieurs dizaines de milliers de lignes, doit-on imposer une pagination serveur stricte par tranches ou implémenter une virtualisation d'affichage sur liste infinie ?
3. **Cadence d'interrogation de l'ingestion des preuves** : Faut-il calquer le polling d'ingestion sur une fréquence fixe ou adopter une cadence adaptative pilotée par l'en-tête `Retry-After` conformément aux préconisations de l'ADR-0008 ?
4. **Règles de troncature pour l'affichage des artefacts volumineux** : Quel seuil de taille ou de lignes retenir pour l'aperçu dans le panneau latéral d'inspection avant de proposer un téléchargement direct de l'observation brute ?
5. **Gestion du comportement d'interface en cas de perte de connectivité prolongée** : Comment l'interface doit-elle notifier l'analyste lorsque la scrutation d'un agent long (ex. scan mémoire Volatility) échoue de manière répétée suite à une coupure réseau locale ?

---

## 10. Grille de Validation et Relecture Croisée

- [x] Chaque écran répertorié dans `docs/frontend/11-ecrans-et-routes.md` correspond à au moins une exigence fonctionnelle (FR).
- [x] L'ensemble des états obligatoires (chargement, vide, erreur, accès refusé, nominal) est explicitement spécifié.
- [x] Chaque exigence non fonctionnelle (NFR) est objectivement formulée avec seuils de performance marqués « à définir ».
- [x] Les cinq comportements d'authentification requis par la consigne sont décrits sous forme de FR distinctes intégrant les décisions D1, D3 et D6 (modèle sans état simple, pas de rotation, déconnexion sans révocation serveur).
- [x] Niveau d'accessibilité aligné sur WCAG 2.1 AA (décision D5), sans exigence AAA.
- [x] Aucune couleur hors palette n'est mentionnée ou référencée.
- [x] Aucun extrait de code informatique n'est présent dans le document.
- [x] Les questions ouvertes restantes sont consignées de manière neutre sans arbitrage prématuré.
- [x] Statut du document : révisé, en attente de validation.

---

**Validation de fond (adéquation aux parcours et vision métier)** :
Product Lead (Abdoul-Gafar AMADOU) - 2026-11-25

**Validation de faisabilité technique (adéquation au socle et conventions)** :
Team Lead (Abdoul-Gafar AMADOU) - 2026-11-25
