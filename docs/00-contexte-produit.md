# 00 - Contexte Produit : IRYX
 
---
 
## 1. Produit
 
**IRYX** est une plateforme d'investigation numérique (DFIR - Digital Forensics and Incident Response) et d'analyse de fraudes, orchestrée par des agents d'intelligence artificielle spécialisés et supervisée par l'humain.
 
Le système permet aux équipes de réponse à incident d'ingérer des preuves numériques brutes (journaux d'événements Windows EVTX, logs textuels, ruches de registre, Prefetch, images mémoire vive RAM), d'en extraire des faits techniques vérifiables de manière déterministe, et d'orienter le raisonnement d'agents IA pour formuler des hypothèses, reconstituer des chronologies d'attaque et générer des rapports d'enquête opposables.
 
---
 
## 2. Personas cibles
 
IRYX cible prioritairement les professionnels de la cybersécurité opérant en Afrique de l'Ouest, confrontés à une asymétrie critique entre l'explosion des incidents et la rareté des compétences spécialisées.
 
### 2.1 Persona 1 : Analyste SOC (Niveau 1 / Niveau 2)
- **Rôle** : Détection, triage initial et qualification des alertes d'incident ou de suspicion de fraude.
- **Besoin principal** : Automatiser la corrélation rapide des volumes massifs d'artefacts hétérogènes sans saturation cognitive, pour décider rapidement du passage en crise forensique.
- **Contrainte** : Délais stricts imposés par les accords de niveau de service (SLA), temps de traitement restreint, expertise inégale sur le parsing bas niveau d'artefacts propriétaires (fichiers EVTX corrompus, structures binaires de registre, symboles mémoire).
 
### 2.2 Persona 2 : Enquêteur numérique / Spécialiste DFIR
- **Rôle** : Conduite d'investigations techniques approfondies post-incident, analyse rétrospective de fraude financière, constitution de dossiers de preuves.
- **Besoin principal** : Rigueur forensique absolue, garantie de la chaîne de possession (chain of custody), élimination des hallucinations d'IA par validation déterministe systématique.
- **Contrainte** : Interdiction absolue d'exfiltrer des données sensibles ou des preuves brutes non pseudonymisées vers des services cloud tiers ; obligation de produire des rapports auditables recevables devant des juridictions ou des régulateurs.
 
### 2.3 Persona 3 : Responsable Sécurité (CISO / RSSI - Afrique de l'Ouest)
- **Rôle** : Pilotage stratégique de la posture de sécurité, communication de crise auprès de la direction générale, justification réglementaire auprès des autorités de protection des données (ex. CDP, ARTCI).
- **Besoin principal** : Visibilité claire, synthétique et chronologique sur les compromissions réelles, limitation des coûts d'investigation externe.
- **Contrainte** : Pénurie aiguë de profils seniors DFIR sur le marché local, budgets contraints, impératif strict de souveraineté opérationnelle et de conformité légale sur les données de paiement et d'identité.
 
---
 
## 3. Problème chiffré et sourcé
 
L'investigation numérique actuelle fait face à un point de rupture structurel :
 
1. **Délai d'identification et de confinement critique** :
   Selon le rapport mondial *IBM Cost of a Data Breach Report 2023*, le délai moyen pour identifier et contenir une violation de données est de **277 jours** (204 jours pour la détection, 73 jours pour le confinement). Le coût moyen global d'une brèche atteint **4,45 millions de dollars**.
2. **Pression accrue sur les marchés émergents d'Afrique de l'Ouest** :
   Selon l'*Interpol African Cyberthreat Assessment Report 2023*, les attaques par rançongiciel et les compromissions d'emails professionnels (BEC / fraude au virement) ont progressé de plus de **30% en un an** en Afrique de l'Ouest. Cette menace frappe un écosystème où le déficit en compétences de cybersécurité dépasse **100 000 spécialistes qualifiés** sur le continent africain (*World Economic Forum Cybersecurity Skills Gap*).
3. **Explosion volumétrique et surcharge des analystes** :
   D'après le *SANS DFIR Survey 2023*, **74% des praticiens forensiques** déclarent que l'inflation du volume de données brutes (images disques de plusieurs centaines de Go, captures RAM de 32 à 128 Go, millions de lignes EVTX) combinée à la fragmentation des outils d'analyse non intégrés constitue le goulot d'étranglement majeur provoquant retards d'enquête et erreurs de diagnostic.
 
---
 
## 4. Promesse de valeur
 
> **IRYX accélère et fiabilise les investigations numériques et l'analyse de fraudes en orchestrant des agents spécialisés guidés par des preuves vérifiables et contrôlés par l'analyste humain.**
 
---
 
## 5. Principes directeurs
 
1. **Evidence-first (Priorité à la preuve)** :
   Aucune affirmation, inférence ou conclusion ne peut exister dans le système sans lien de traçabilité direct vers une observation matérielle issue d'une preuve brute immuable.
2. **Human-in-the-loop (Contrôle humain incontournable)** :
   L'intelligence artificielle assiste l'investigateur mais ne prend aucune décision opérationnelle finale en autonomie. Trois portes de contrôle humain (H1, H2, H3) sanctuarisent le cycle de vie de chaque enquête.
3. **Séparation stricte des responsabilités** :
   Chaque rôle d'agent accomplit une tâche dédiée et étanche. L'agent qui planifie ne manipule pas les preuves ; l'agent qui exécute ne porte pas de jugement ; le module qui vérifie est strictement déterministe et n'utilise aucun modèle probabiliste (LLM).
4. **Résultats persistés et reproductibles** :
   Chaque plan, exécution d'outil, observation et validation intermédiaire est persisté en base relationnelle. Une enquête peut être interrompue, reprise ou auditée a posteriori avec un résultat identique.
5. **Exécution contrôlée et sécurisée** :
   Tout outil technique s'exécute dans un environnement isolé, avec réseau désactivé, compte non-root et accès aux preuves monté exclusivement en lecture seule.
6. **Monolithe modulaire** :
   Le système est conçu comme une architecture logicielle unifiée, modulaire, facilement déployable sur un serveur unique via Docker Compose, éliminant la complexité de maintenance des microservices pour le MVP.
 
---
 
## 6. Glossaire
 
- **Dossier (`Case`)** : Entité organisationnelle regroupant l'ensemble des preuves, métadonnées, exécutions d'outils, observations, findings et rapports rattachés à une affaire d'investigation donnée.
- **Preuve (`Evidence`)** : Fichier numérique brut ou artefact physique importé dans un dossier (image disque, dump mémoire, archive de journaux), scellé par une empreinte cryptographique SHA-256 dès son ingestion.
- **Course d'ingestion (`IngestionRun`)** : Opération asynchrone enregistrant une preuve, calculant son empreinte, vérifiant son intégrité et identifiant son type MIME réel.
- **Observation (`Observation`)** : Donnée technique unitaire structurée et normalisée (horodatage UTC, entité concernée, attributs), extraite d'une preuve par un outil d'investigation avec indication précise de sa localisation source.
- **Outil / Exécution d'outil (`ToolExecution`)** : Exécution tracée d'un parseur ou utilitaire technique autorisé de la liste blanche (ex. analyseur EVTX, Volatility 3, regipy), opérée via la Gateway sécurisée avec enregistrement de ses paramètres, sa durée et l'empreinte de sa sortie.
- **Finding (`Finding`)** : Fait technique avéré, inférence analytique ou hypothèse qualifiée, produit par l'analyste ou un agent, obligatoirement indexé sur une ou plusieurs observations vérifiées.
- **Porte de contrôle (`Gate`)** : Point de synchronisation et de blocage obligatoire imposant une vérification déterministe ou une validation humaine avant le passage à la phase suivante.
- **Revue humaine (`Human Review`)** : Action explicite d'un utilisateur habilité validant le plan d'action (porte H1), validant les findings (porte H2) ou autorisant l'envoi d'une synthèse pseudonymisée à un LLM externe (porte H3).
- **Événement d'audit (`AuditEvent`)** : Enregistrement immuable, consigné dans un journal en ajout seul, traçant l'identité de l'acteur, l'action exécutée, la cible, l'horodatage et l'empreinte du contenu.
 
---
 
Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
