# 11 - Écrans et Routes : Structure de Navigation Front-End

---

## 1. Référentiel des routes de l'application

Le découpage applicatif repose sur une structure hiérarchique articulée autour du dossier d'investigation :

| Route | Désignation écran | Étape liée | Niveau d'accès |
|---|---|---|---|
| `/login` | Écran d'authentification | Hors cycle dossier | Public non authentifié |
| `/cases` | Liste des dossiers de l'organisation | Hors cycle dossier | Utilisateur authentifié |
| `/cases/:caseId` | Tableau de bord et contexte | Étape 1 : Contexte | Membre du dossier |
| `/cases/:caseId/evidence` | Registre et téléversement des preuves | Étape 2 : Preuves | Membre du dossier |
| `/cases/:caseId/evidence/:evidenceId` | Panneau de détail d'une preuve | Étape 2 : Preuves | Membre du dossier |
| `/cases/:caseId/plan` | Revue du plan et arbitrage H1 | Étape 3 : Plan et agents | Membre ; arbitrage réservé aux analystes |
| `/cases/:caseId/run` | Console d'exécution des agents | Étape 3 : Plan et agents | Membre du dossier |
| `/cases/:caseId/results` | Exploration des résultats (chronologie, artefacts, hypothèses) | Étape 4 : Résultats | Membre du dossier |
| `/cases/:caseId/review` | Revue H2 des findings et autorisation H3 | Étape 5 : Revue et rapport | Analyste habilité |
| `/cases/:caseId/report` | Génération et téléchargement du rapport scellé | Étape 5 : Revue et rapport | Membre du dossier |

---

## 2. Éléments permanents d'encadrement

### 2.1 Barre supérieure (Top Bar)
Présente de manière transverse sur l'ensemble des écrans authentifiés, elle comprend :
- Le logo officiel IRYX.
- La dénomination de l'organisation active.
- L'identité de l'utilisateur connecté (nom, prénom et rôle).
- Le bouton de déconnexion explicite avec invalidation de session.

### 2.2 Barre latérale de navigation du dossier (Sidebar)
Présente sur l'ensemble des routes débutant par `/cases/:caseId/`, elle matérialise le cycle séquentiel de l'enquête :
- En-tête : titre du dossier courant et identifiant tronqué avec copie presse-papier.
- Les cinq étapes numérotées accompagnées de leur indicateur d'état (non démarrée, en cours, terminée, bloquée par une porte) :
  1. Contexte (`/cases/:caseId`)
  2. Preuves (`/cases/:caseId/evidence`)
  3. Plan et agents (`/cases/:caseId/plan` et `/cases/:caseId/run`)
  4. Résultats (`/cases/:caseId/results`)
  5. Revue et rapport (`/cases/:caseId/review` et `/cases/:caseId/report`)
- Pied de barre latérale : encart institutionnel rappelant la politique de confidentialité locale (traitement sécurisé et preuves préservées en environnement contrôlé).
- Règle d'accès : la consultation d'une étape reste toujours accessible ; en revanche, les actions de soumission ou de validation sont grisées tant que les conditions préalables ne sont pas satisfaites, avec mention explicite du motif.

---

## 3. Spécification détaillée des écrans et états obligatoires

Chaque écran de la plateforme intègre obligatoirement la prise en charge exhaustive de cinq états d'affichage : l'état de chargement, l'état vide, l'état d'erreur technique, l'état d'accès refusé, ainsi que l'état métier nominal.

### 3.1 Écran de connexion (`/login`)
- **Rôle fonctionnel** : Authentification initiale de l'utilisateur par formulaire sécurisé.
- **Contenu** : Logo IRYX, champ identifiant / adresse électronique, champ mot de passe masqué, bouton de soumission « Se connecter ».
- **Actions** : Validation et envoi du formulaire. Redirection automatique vers `/cases` en cas de succès, ou vers la ressource initialement demandée.
- **États obligatoires** :
  - *État de chargement* : Désactivation des champs et du bouton, affichage d'un indicateur de traitement sur le bouton.
  - *État vide* : Affichage nominal du formulaire prêt pour la saisie utilisateur.
  - *État d'erreur* : Message d'erreur unique « Identifiants incorrects » (sans préciser la validité respective du compte ou du mot de passe) ; bandeau d'erreur réseau en cas d'indisponibilité de l'API.
  - *État d'accès refusé* : Sans objet (accès public).
  - *État métier nominal* : Formulaire de connexion interactif.

### 3.2 Liste des dossiers (`/cases`)
- **Rôle fonctionnel** : Panorama des affaires d'investigation ouvertes ou archivées au sein de l'organisation.
- **Contenu** : Tableau récapitulatif paginé (titre du dossier, statut courant, date de création UTC, quantité de preuves rattachées), champ de filtrage par texte libre, bouton de création « Nouveau dossier ».
- **Fenêtre modale de création** : Titre obligatoire, description synthétique, date et heure de détection de l'incident, typologie de l'incident, périmètre des actifs concernés.
- **Actions** : Sélection d'un dossier (redirection vers son contexte), ouverture de la fenêtre de création, pagination et filtrage.
- **États obligatoires** :
  - *État de chargement* : Lignes de substitution animées (squelette de chargement) dans le tableau.
  - *État vide* : Message informatif « Aucun dossier d'investigation enregistré. Créez votre premier dossier. » accompagné du bouton d'action principal.
  - *État d'erreur* : Notification d'échec de récupération avec message descriptif et bouton « Réessayer ».
  - *État d'accès refusé* : Redirection vers l'authentification si la session est expirée ou invalide.
  - *État métier nominal* : Grille de dossiers interactive avec pagination serveur active.

### 3.3 Contexte du dossier (`/cases/:caseId`)
- **Rôle fonctionnel** : Présentation des éléments administratifs, techniques et opérationnels cadrant l'incident.
- **Contenu** : Fiche synthétique du dossier (titre, description de l'incident, typologie, systèmes impactés, dates d'activité, statut du dossier), liste des membres habilités (consultation seule au MVP).
- **Actions** : Modification des métadonnées du dossier par un analyste titulaire ; changement manuel du statut global (ouvert, en cours, terminé).
- **États obligatoires** :
  - *État de chargement* : Blocs de substitution animés sur la fiche d'informations.
  - *État vide* : Affichage de mentions par défaut pour les champs optionnels non renseignés.
  - *État d'erreur* : Écran d'erreur de chargement du dossier avec possibilité de rafraîchissement.
  - *État d'accès refusé* : Blocage de consultation et redirection immédiate vers `/cases` avec le message d'alerte « Vous n'avez pas accès à ce dossier ».
  - *État métier nominal* : Fiche d'informations complète et éditable selon les privilèges de l'analyste.

### 3.4 Registre des preuves (`/cases/:caseId/evidence`)
- **Rôle fonctionnel** : Espace d'acquisition, de scellement cryptographique et d'inventaire des éléments matériels de l'enquête.
- **Contenu** : Zone de glisser-déposer de fichiers volumineux, tableau des preuves (intitulé d'origine, typologie binaire détectée, volume en octets, empreinte SHA-256 tronquée avec fonction de copie, statut d'ingestion, horodatage UTC, opérateur), bandeau permanent d'intégrité légale.
- **Actions** : Sélection multiple de fichiers à téléverser, annulation d'envoi en cours, consultation des détails par ouverture du panneau latéral, déclenchement de la phase d'analyse via le bouton « Lancer l'analyse ».
- **États obligatoires** :
  - *État de chargement* : Indicateur de chargement de la liste des preuves déjà archivées.
  - *État vide* : Zone de dépôt mise en avant avec indication des formats admissibles (EVTX, logs, ruches de registre, Prefetch, images mémoire) et mention « Aucune preuve déposée pour ce dossier ».
  - *État d'erreur* : Échec d'ingestion signalé avec libellé explicite et lien d'ouverture du journal d'erreur ; notification en cas de rejet immédiat d'un fichier (format non supporté ou taille hors limite).
  - *État d'accès refusé* : Masquage total de la vue et notification d'absence de droits.
  - *État métier nominal* : Registre des preuves synchronisé avec bouton « Lancer l'analyse » actif si au moins une preuve est confirmée intègre (ou désactivé avec motif si aucune preuve n'est intègre).

### 3.5 Panneau de détail d'une preuve (`/cases/:caseId/evidence/:evidenceId`)
- **Rôle fonctionnel** : Inspection technique approfondie et chaîne de possession d'un artefact numérique.
- **Contenu** : Panneau coulissant latéral sur la liste des preuves. Affiche l'empreinte SHA-256 intégrale en typographie à chasse fixe, l'historique complet des tentatives d'ingestion, le décompte des observations extraites, et les métadonnées techniques du conteneur.
- **Actions** : Copie intégrale de l'empreinte, fermeture du panneau (retour à la vue de liste), navigation directe par URL partageable.
- **États obligatoires** :
  - *État de chargement* : Squelette de chargement des détails et métadonnées.
  - *État vide* : Mention « Aucune observation extraite » si la preuve a été traitée sans découverte d'artefacts.
  - *État d'erreur* : Notification d'impossibilité de charger les métadonnées de la preuve.
  - *État d'accès refusé* : Fermeture du panneau avec message de restriction d'accès.
  - *État métier nominal* : Affichage complet des métadonnées et observations rattachées.

### 3.6 Plan d'investigation et porte H1 (`/cases/:caseId/plan`)
- **Rôle fonctionnel** : Arbitrage formel de l'analyste sur la stratégie technique proposée par l'agent Planner.
- **Contenu** : Liste ordonnée des étapes d'outils planifiées (objectif opérationnel de l'étape, agent assigné, outil forensique mobilisé, preuves ciblées), historique de validation.
- **Actions** :
  - Validation du plan complet (déclenchement de la porte H1).
  - Suppression unitaire d'une étape avant confirmation.
  - Rejet argumenté du plan avec saisie d'un motif obligatoire (relance automatique du Planner).
- **États obligatoires** :
  - *État de chargement / En cours de planification* : Écran d'attente animé avec message « Élaboration du plan par le Planner en cours... » actualisé par scrutation (polling).
  - *État vide* : Notification « Aucun outil forensique applicable aux preuves disponibles » avec invitation à importer de nouveaux artefacts.
  - *État d'erreur* : Échec de l'agent Planner avec affichage de la cause et bouton de régénération.
  - *État d'accès refusé* : Consultation seule pour les profils non analystes (boutons de validation masqués).
  - *État métier nominal* : Plan prêt pour arbitrage avec actions de validation ou rejet disponibles ; bascule en lecture seule après validation H1 avec horodatage et identité de l'analyste.

### 3.7 Console d'exécution des agents (`/cases/:caseId/run`)
- **Rôle fonctionnel** : Supervision de l'orchestration asynchrone des agents et parseurs spécialisés.
- **Contenu** : Cartes individuelles par agent (Planner, Executor, Analyst, Verifier, Corrélateur, Rapporteur) indiquant le statut opérationnel et la barre de complétion ; étape en cours d'exécution ; flux d'activité textuel horodaté en UTC.
- **Actions** : Suspension temporaire du traitement, reprise de session, interruption définitive avec dialogue de confirmation obligatoire ; bouton de relance sélective pour un agent en échec.
- **États obligatoires** :
  - *État de chargement* : Initialisation de la session d'exécution.
  - *État vide* : Mention « Aucune session d'investigation lancée. Validez préalablement le plan en étape 3. »
  - *État d'erreur / Échec partiel* : Mise en évidence visuelle de l'agent en échec avec affichage du diagnostic technique et option « Réessayer cet agent », sans bloquer les autres agents en cours.
  - *État d'accès refusé* : Affichage bloqué si l'utilisateur n'est pas autorisé sur le dossier.
  - *État métier nominal* : Console interactive avec interrogation périodique toutes les deux secondes, se stabilisant dès l'atteinte d'un état terminal (terminé, échoué, annulé). Mise en avant du bouton « Voir les résultats » à l'issue de l'exécution.

### 3.8 Exploration des résultats (`/cases/:caseId/results`)
- **Rôle fonctionnel** : Synthèse unifiée des observations techniques consolidées à travers trois onglets.
- **Contenu** :
  - *Onglet Chronologie* : Liste séquentielle unifiée des événements triée par horodatage UTC, filtrable par typologie d'artefact et plage temporelle ; chaque ligne expose la date UTC, un résumé factuel et la source cliquable ouvrant le tiroir latéral d'inspection.
  - *Onglet Artefacts* : Répertoire exhaustif des entités extraites (entrées de registre, exécutions de programmes, journaux) indexées par outil d'extraction.
  - *Onglet Hypothèses* : Liste préparatoire des findings (faits techniques, inférences analytiques, hypothèses de compromission) avec niveau de confiance (lecture seule à ce stade).
- **Actions** : Changement d'onglet, application des filtres temporels, ouverture du tiroir de preuve source.
- **États obligatoires** :
  - *État de chargement* : Indicateur d'agrégation des résultats.
  - *État vide* : Message « Aucun résultat exploitable généré pour ce dossier » avec lien de redirection vers le plan d'investigation.
  - *État d'erreur / Résultats partiels* : Bannière signalant que certains résultats sont incomplets en raison d'échecs sur des agents spécifiques.
  - *État d'accès refusé* : Accès interdit en l'absence de droits sur le dossier.
  - *État métier nominal* : Données filtrables et navigables avec ouverture instantanée du panneau de source d'observation.

### 3.9 Revue des findings et autorisation H3 (`/cases/:caseId/review`)
- **Rôle fonctionnel** : Contrôle qualité forensique final (porte H2) et arbitrage sur l'ouverture externe (porte H3).
- **Contenu** :
  - *Section Porte H2* : Liste détaillée des findings préqualifiés par le Verifier (titre, niveau de sévérité, typologie, score de confiance, références de preuves attachées).
  - *Section Porte H3* : Encart de vérification de la synthèse pseudonymisée destinée au modèle de langage externe, listant expressément les éléments masqués (adresses IP, identifiants, hôtes), assorti d'une case à cocher impérative « J'autorise l'envoi de cette synthèse pseudonymisée ».
- **Actions** : Décision unitaire par finding (valider, rejeter, annoter) ; acceptation ou refus de la transmission H3 ; bouton de lancement du rapport (restant désactivé tant qu'aucun finding n'est validé).
- **États obligatoires** :
  - *État de chargement* : Récupération des findings et de la prévisualisation de pseudonymisation.
  - *État vide* : Message « Aucune hypothèse disponible pour revue » (génération de rapport désactivée).
  - *État d'erreur* : Échec de chargement des synthèses ou indisponibilité du service de pseudonymisation.
  - *État d'accès refusé* : Accès strictement restreint aux seuls utilisateurs porteurs du rôle analyste.
  - *État métier nominal* : Interface d'arbitrage complète permettant la validation pas à pas et le déblocage conditionnel de la génération du rapport.

### 3.10 Génération et consultation du rapport (`/cases/:caseId/report`)
- **Rôle fonctionnel** : Restitution éditoriale, scellement documentaire et archivage de l'enquête.
- **Contenu** : Prévisualisation paginée du rapport d'incident complet (synthèse managériale, périmètre analysé, méthodologie et outils, chaîne des preuves, observations consolidées, constats validés en H2, chronologie des faits, limites techniques) ; tableau d'historique des versions publiées.
- **Actions** : Déclenchement de la compilation, téléchargement direct du fichier scellé (formats Markdown, PDF ou JSON), sélection d'un rapport antérieur dans l'historique.
- **États obligatoires** :
  - *État de chargement / En génération* : Écran d'attente avec indicateur d'avancement actualisé par scrutation régulière.
  - *État vide* : Mention « Aucun rapport finalisé pour ce dossier. Déclenchez la génération ci-dessus. »
  - *État d'erreur* : Notification d'échec de compilation avec possibilité de réessai immédiat.
  - *État d'accès refusé* : Consultation refusée aux tiers non membres du dossier.
  - *État métier nominal* : Visualiseur de rapport complet interactif et boutons de téléchargement d'archives certifiées.

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-25
