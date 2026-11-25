# 15. Consignation des décisions ouvertes du front-end IRYX

Date d'effet : 2026-11-25
Statut global : **décidé**

Le présent document consigne formellement les arbitrages rendus sur les paramètres d'architecture et points ouverts identifiés lors des phases de spécification du front-end. Ces décisions s'appliquent exclusivement au front-end IRYX et ne s'appliquent pas à la configuration du back-end.

---

## 1. Décision C1 — Seuil de performance FCP (First Contentful Paint)

- **Identifiant** : C1 (NFR-PERF-01)
- **Statut** : **décidé**
- **Date** : 2026-11-25
- **Décision arrêtée** :
  - La mesure du FCP sera réalisée après la première démonstration opérationnelle.
  - Aucun chiffre ni seuil quantitatif n'est fixé aujourd'hui.
  - En conséquence, aucune valeur de seuil n'est écrite dans le code source ni dans les critères chiffrés des stories front-end.

---

## 2. Décision C2 — Réactivité aux interactions et transitions d'interface

- **Identifiant** : C2 (NFR-PERF-02)
- **Statut** : **décidé**
- **Date** : 2026-11-25
- **Décision arrêtée** :
  - Principe d'immédiateté retenu : toute action locale de l'analyste se reflète à l'écran sans attendre le serveur.
  - Application d'un affichage optimiste pour la navigation et les transitions locales.
  - Affichage systématique d'un indicateur de chargement (lignes de squelettes ou spinner) pour l'attente des appels réseau.
  - Aucun seuil chiffré n'est imposé dans le code.

---

## 3. Décision C4 — Politique d'inactivité de l'analyste

- **Identifiant** : C4
- **Statut** : **décidé**
- **Date** : 2026-11-25
- **Décision arrêtée** :
  - Aucune déconnexion automatique sur inactivité au périmètre du MVP.
  - Les évolutions post-MVP relatives à un timer d'inactivité devront être consignées dans une ADR dédiée.
  - La sécurité repose sur la durée de vie courte du jeton d'accès Bearer en mémoire vive volatile (15 minutes, décision D3), limitant strictement la fenêtre d'exposition en cas d'abandon de poste.

---

## 4. Décision Identité Utilisateur — Source des données de profil et neutralité

- **Identifiant** : Identité utilisateur (Story F1.5 / F1.6)
- **Statut** : **décidé**
- **Date** : 2026-11-25
- **Décision arrêtée** :
  - L'identité de l'analyste (nom, rôle opérationnel, organisation détentrice) provient exclusivement du serveur back-end, soit par la réponse du formulaire de connexion, soit par une route `/me` enrichie.
  - Le front-end s'interdit formellement d'inventer la moindre donnée d'identité et n'expose aucun endpoint ni formulaire de profil propre.
  - Les valeurs neutres institutionnelles « **Utilisateur** » et « **Organisation** » sont rigoureusement maintenues dans l'interface tant que le contrat d'API réel n'est pas stabilisé et raccordé.

---

## 5. Décision DP-05 — Seuil de coupure réseau pour la scrutation

- **Identifiant** : DP-05 (NFR-PERF-03)
- **Statut** : **à décider**
- **Date** : 2026-11-25
- **Décision consignée** :
  - Le seuil de déclenchement de la coupure réseau prolongée (positionné par défaut technique à 3 échecs consécutifs de transport HTTP) n'est pas une décision validée.
  - La valeur numérique précise reste « à décider ».
  - Le comportement d'interface reste en place conformément à DP-05 : en cas d'erreurs répétées, l'interrogation automatique de l'API est interrompue pour protéger l'infrastructure et un bouton « Réessayer la connexion » est mis à la disposition de l'opérateur.

---

*Note de portée : Ces décisions ne s'appliquent pas à la configuration du back-end.*
