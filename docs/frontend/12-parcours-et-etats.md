# 12 - Parcours et États : Scénarios Utilisateurs et Machines d'États

---

## 1. Parcours utilisateur principal (Scénario de démonstration)

Le parcours de référence couvre l'ensemble des fonctionnalités du MVP, depuis l'authentification jusqu'à l'export du rapport certifié, en dix étapes séquentielles. La durée cible totale est inférieure à dix minutes pour un opérateur formé :

1. **Connexion sécurisée** :
   L'analyste accède à la route `/login`, renseigne ses identifiants et valide le formulaire. Le système délivre le jeton d'accès conservé en mémoire vive (sans aucun stockage dans localStorage ni sessionStorage, et sans cookie pour les requêtes métier) puis redirige l'opérateur vers l'écran `/cases`.
2. **Création d'un nouveau dossier d'investigation** :
   Depuis `/cases`, l'analyste clique sur « Nouveau dossier », remplit les métadonnées de l'incident (titre, description factuelle, date de survenance, typologie de crise, systèmes cibles) et valide. L'application bascule sur `/cases/:caseId`.
3. **Dépôt et scellement des preuves matérielles** :
   L'analyste navigue vers l'étape 2 (`/cases/:caseId/evidence`), dépose par glisser-déposer deux artefacts de test (un journal d'événements Windows EVTX et une image de mémoire vive de démonstration). L'interface affiche la jauge de transfert pour chaque fichier, puis bascule sur le suivi d'ingestion asynchrone.
4. **Contrôle d'intégrité et lancement de l'analyse** :
   Une fois les empreintes SHA-256 calculées et les formats validés avec le statut intègre, le bouton « Lancer l'analyse » devient actif. L'analyste clique pour engager le cycle d'investigation.
5. **Revue du plan et arbitrage en porte H1** :
   L'analyste est orienté sur `/cases/:caseId/plan`. Il consulte la liste ordonnée des étapes d'analyse forensique élaborée par l'agent Planner. Après examen des outils et paramètres proposés, l'analyste valide le plan tel quel pour franchir formellement la porte H1.
6. **Supervision de l'exécution des agents** :
   L'écran `/cases/:caseId/run` affiche l'activité en temps réel des agents spécialisés (Executor, Analyst, Verifier, Corrélateur). L'analyste suit la progression des cartes d'agents et le journal d'activité horodaté en UTC jusqu'à l'état terminé de la session.
7. **Exploration des résultats et vérification de la source** :
   L'analyste clique sur « Voir les résultats » pour atteindre `/cases/:caseId/results`. Il consulte la chronologie unifiée des faits techniques, applique un filtre sur les événements clés, puis clique sur une entrée pour ouvrir le panneau d'inspection de la source et vérifier l'extrait brut de l'artefact.
8. **Revue qualitative des findings en porte H2** :
   Sur l'écran `/cases/:caseId/review`, l'analyste examine les constats qualifiés par le Verifier. Il valide deux findings confirmés par les preuves et rejette une hypothèse non concluante, enregistrant ainsi ses décisions pour la porte H2.
9. **Arbitrage de confidentialité en porte H3 et génération du rapport** :
   Toujours sur `/cases/:caseId/review`, l'analyste choisit de refuser l'envoi vers le modèle externe afin de garantir le confinement strict des données sur l'infrastructure locale. Il sélectionne la génération locale du rapport d'incident.
10. **Consultation et téléchargement du livrable final** :
    L'analyste accède à `/cases/:caseId/report`, prévisualise la structure du document compilé (résumé, chronologie, observations, findings validés, limites) et télécharge l'archive scellée au format PDF.

---

## 2. Parcours d'erreur et comportements d'interface attendus

Le tableau ci-dessous répertorie les huit situations d'anomalie prévues par le plan d'exécution et les réponses strictes imposées à l'interface :

| Cas d'erreur | Événement déclencheur | Comportement attendu du front-end |
|---|---|---|
| Fichier refusé à l'ingestion | Fichier non conforme (extension ou signature non supportée) ou taille supérieure à la limite autorisée | Rejet immédiat avec message explicite précisant la raison du refus ; aucun enregistrement ni ligne fantôme créée dans la liste des preuves. |
| Altération d'intégrité de preuve | Empreinte SHA-256 recalculée non concordante avec le scellement initial | Marquage visuel de la preuve comme « non intègre » ; désactivation automatique du bouton d'analyse sur cet élément avec avertissement de sécurité. |
| Plan d'investigation vide | Aucun outil forensique de la liste blanche n'est applicable aux types de preuves déposées | Affichage d'un état vide informatif expliquant l'absence d'outils compatibles et bouton de retour immédiat vers l'étape des preuves. |
| Échec d'exécution d'un agent | Erreur d'exécution technique ou dépassement de délai sur un agent spécifique | La carte de l'agent concerné bascule à l'état d'échec avec affichage du diagnostic technique et d'un bouton « Réessayer cet agent » ; l'exécution des autres agents n'est pas interrompue. |
| Expiration de session utilisateur | Réponse HTTP 401 renvoyée par l'API sur une requête authentifiée | Redirection transparente vers l'écran `/login` avec préservation de l'URL cible, et réorientation vers la page initiale une fois la nouvelle connexion établie. |
| Accès non autorisé à un dossier | Réponse HTTP 403 lors d'une tentative d'accès à un dossier dont l'utilisateur n'est pas membre | Redirection vers `/cases` assortie d'une notification d'accès refusé ; aucune donnée sensible du dossier ciblé n'est exposée. |
| Indisponibilité du serveur API | Erreur réseau globale ou réponse HTTP de classe 5xx | Bandeau permanent d'alerte en haut d'écran avec proposition de réessai ; conservation en mémoire locale des saisies et transferts en cours pour éviter toute perte de données. |
| Défaillance du modèle externe | Indisponibilité ou erreur de communication lors d'une sollicitation externe en porte H3 | Message d'information sur la rupture de connectivité externe et proposition de bascule immédiate vers le moteur de génération locale du rapport. |

---

## 3. Référentiel des machines d'états affichées

Afin de garantir une synchronisation stricte avec le modèle de données back-end (document `docs/03-modele-de-donnees.md`), l'interface consomme et restitue les statuts métier suivants sans altération de terminologie :

### 3.1 Cycle de vie de l'ingestion (`IngestionRun`)
- `pending` (en attente) : Enregistrement initial de la preuve dans la file de traitement.
- `processing` (en cours) : Calcul de l'empreinte cryptographique et identification de signature.
- `completed` (terminée) : Scellement achevé avec succès, preuve déclarée intègre.
- `failed` (en échec) : Rupture de transfert, format binaire invalide ou corruption de fichier.

### 3.2 Cycle de vie de la session d'investigation (`InvestigationRun`)
- `pending` (en attente) : Session créée, en attente de prise en charge par l'orchestrateur.
- `running` (en cours) : Exécution active de la chaîne d'outils ou des agents d'analyse.
- `paused` (en pause) : Traitement suspendu sur demande explicite de l'analyste.
- `completed` (terminée) : Ensemble des étapes d'analyse achevées avec succès.
- `failed` (en échec) : Interruption critique non recouvrable de la session d'enquête.

Phases associées au sein de l'investigation (`current_phase`) :
`triage` -> `planning` -> `execution` -> `analysis` -> `verification` -> `reporting`.

### 3.3 Statut d'exécution d'un agent spécialisé (`Phase` / exécution d'agent)
- `pending` (en attente) : Agent programmé dans le plan, en attente de son tour d'exécution.
- `active` / en cours : Agent mobilisé sur le traitement de ses artefacts.
- `completed` (terminé) : Tâche de l'agent exécutée et certifiée conforme.
- `failed` (en échec) : Incident technique ou erreur d'exécution sur le composant.

### 3.4 Statut d'un constat d'enquête (`Finding`)
- `proposed` (proposé) : Constat généré par l'agent Analyst et validé par le Verifier, soumis à l'arbitrage humain en porte H2.
- `validated` (validé) : Constat formellement approuvé par l'analyste humain pour intégration au rapport.
- `rejected` (rejeté) : Constat écarté ou réfuté par l'analyste lors de la revue.

### 3.5 Cycle de vie du rapport d'enquête (`Report`)
- `draft` (en génération / brouillon) : Compilation et mise en forme du document en cours.
- `validated` (prêt / validé) : Rapport finalisé, scellé par empreinte SHA-256 et disponible pour consultation.
- `exported` (téléchargé / exporté) : Rapport extrait sous un format externe par l'opérateur.

---

## 4. Règle de robustesse face aux états inconnus

Si l'API transmet une valeur de statut non répertoriée dans le référentiel ci-dessus (ex. évolution de version du back-end ou enrichissement fonctionnel futur), le front-end applique la règle de résilience suivante :
- Le statut est affiché sous la forme « État inconnu » suivi du code textuel brut retourné entre parenthèses.
- L'écran ne subit aucun blocage, crash ou interruption d'affichage.
- Les actions dépendantes de ce statut adoptent par mesure de sécurité l'état désactivé avec mention explicite de l'indisponibilité.

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-25
