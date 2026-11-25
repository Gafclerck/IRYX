# 10 - Contexte Front-End : IRYX

---

## 1. Rôle et mission de l'interface front-end

L'interface front-end d'**IRYX** constitue le poste de travail visuel et interactif destiné aux équipes de réponse à incident (DFIR) et d'investigation numérique. Elle matérialise le flux complet de traitement d'un incident, depuis l'import des artefacts bruts jusqu'à la restitution du rapport d'enquête opposable.

Le front-end a pour mandat de fournir une visibilité limpide sur les actions menées par les agents d'intelligence artificielle, d'offrir une ergonomie cognitive adaptée aux situations d'urgence opérationnelle, et de matérialiser de façon inviolable les portes de contrôle humain (gates H1, H2, H3).

---

## 2. Utilisateurs cibles (Personas)

Conformément au document de cadrage produit, le front-end s'adresse à trois profils opérationnels complémentaires :

### 2.1 Analyste SOC (Niveau 1 / Niveau 2)
- **Objectif** : Triage initial, ingestion rapide des preuves et qualification des alertes d'incident ou de fraude financière.
- **Besoins dans l'interface** : Suivi visuel immédiat des statuts d'ingestion et des contrôles d'intégrité, navigation fluide sans surcharge cognitive, identification claire des anomalies et chronologies.
- **Contraintes** : Respect d'accords de niveau de service (SLA) stricts, manipulation d'artefacts techniques hétérogènes.

### 2.2 Enquêteur numérique / Spécialiste DFIR
- **Objectif** : Conduite d'investigations forensiques approfondies et analyse rétrospective d'incident.
- **Besoins dans l'interface** : Accès direct aux sources brutes (panneau d'observation, empreintes SHA-256 complètes, horodatages UTC précis), validation fine des hypothèses et constats (findings) en porte H2, traçabilité absolue de la chaîne de possession.
- **Contraintes** : Rigueur méthodologique, impossibilité de masquer les erreurs d'outils, rejet formel des hallucinations d'IA via vérification déterministe.

### 2.3 Responsable Sécurité (CISO / RSSI)
- **Objectif** : Supervision stratégique de l'incident, arbitrage sur le partage externe de données en porte H3, génération et consultation des rapports de synthèse.
- **Besoins dans l'interface** : Tableau de bord consolidé du dossier, clarté des synthèses de risques et sévérités, historique scellé des rapports opposables.
- **Contraintes** : Respect scrupuleux des réglementations de protection des données et souveraineté opérationnelle.

---

## 3. Principes directeurs de l'interface

1. **Le front reflète le back-end, il ne le décide pas** :
   Les statuts affichés (état d'un dossier, d'une ingestion, d'un agent, d'un finding ou d'un rapport) proviennent directement de l'API. Aucune règle de calcul métier ni déduction d'état n'est exécutée en autonomie côté navigateur.
2. **Navigation calquée sur les cinq étapes du canevas** :
   La barre latérale d'un dossier matérialise en permanence les cinq étapes séquentielles : Contexte, Preuves, Plan et agents, Résultats, Revue et rapport.
3. **Portes humaines infranchissables (Human-in-the-Loop Gates)** :
   Trois portes bloquent visuellement et logiquement l'avancement :
   - Porte H1 : validation du plan d'investigation proposé par l'agent Planner avant exécution des outils.
   - Porte H2 : validation individuelle des constats et hypothèses formulés par l'agent Analyst.
   - Porte H3 : autorisation explicite de l'analyste avant transmission d'une synthèse pseudonymisée vers un grand modèle de langage externe.
   Aucune action d'interface ne peut contourner ou masquer ces portes.
4. **Sombre d'abord (Dark mode exclusif)** :
   Le thème sombre est l'unique thème supporté au MVP. Il s'appuie strictement sur la palette officielle à cinq couleurs figée dans les jetons de design.
5. **Français intégral** :
   L'ensemble des libellés, messages d'état, alertes, formulaires et rapports est rédigé en langue française. Aucune internationalisation n'est intégrée au MVP.
6. **Poste de travail fixe (Desktop-first)** :
   L'application est conçue pour des écrans professionnels d'une résolution horizontale minimale de 1280 pixels. Aucune adaptation pour appareils mobiles ou tablettes n'est prévue au MVP.
7. **Suivi asynchrone par interrogation périodique (Polling)** :
   Conformément à la décision D-24, les traitements longs (tâches d'ingestion, sessions d'agents, génération de rapports) sont actualisés par interrogation régulière de l'API REST sans recours aux technologies WebSocket ou SSE.

---

## 4. Périmètre fonctionnel MVP du front-end

Le périmètre retenu pour le MVP couvre dix écrans et fonctionnalités clés :
- Écran de connexion avec gestion de session sécurisée.
- Liste et création des dossiers d'investigation avec pagination serveur.
- Tableau de bord de contexte du dossier (métadonnées, membres en consultation, statut global).
- Module de gestion des preuves numériques : téléversement unitaire ou groupé avec progression en temps réel, calcul et affichage d'empreinte SHA-256, panneau latéral d'inspection des observations brutes.
- Écran de revue du plan d'investigation et arbitrage H1 (retrait d'étapes ou validation globale).
- Console de suivi d'exécution des agents spécialisés avec journalisation horodatée en UTC et contrôle de session (pause, reprise, annulation).
- Espace de consultation des résultats articulé en trois vues : chronologie unifiée des faits, inventaire des artefacts extraits, liste des hypothèses.
- Panneau d'inspection de la source pour tout événement de la chronologie.
- Interface d'arbitrage H2 (validation, rejet, annotation des findings) et autorisation explicite H3 (pseudonymisation vérifiable).
- Module de génération, historique et téléchargement scellé des rapports d'enquête (formats Markdown, PDF, JSON).

---

## 5. Exclusions et reports explicites du MVP

Sont formellement exclus du périmètre initial du front-end :
- Ajout manuel libre d'étapes au sein du plan d'investigation (seul le retrait d'étapes proposées par l'agent est supporté).
- Administration avancée des comptes utilisateurs, attribution dynamique des permissions et gestion des rôles organisationnels depuis l'interface (gérées au niveau système).
- Écran dédié de consultation du journal d'audit immuable (persistance assurée côté back-end).
- Mode d'affichage clair ou thèmes alternatifs.
- Support multilingue ou localisation dynamique.
- Déclinaison mobile ou conteneur d'application bureau (ex. Tauri ou Electron).
- Visualisations graphiques nodales complexes : la chronologie est traitée sous forme de liste séquentielle linéaire filtrable.
- Éléments collaboratifs en temps réel (édition concurrente, présence multi-curseurs).

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-25
