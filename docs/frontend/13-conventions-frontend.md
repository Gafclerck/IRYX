# 13 - Conventions Front-End : Architecture, Stack et Charte Visuelle

---

## 1. Choix technologiques figés (D-27 à D-43)

Conformément à la gouvernance technique du projet, les décisions suivantes fixent le socle technologique intangibles du front-end IRYX :

| Identifiant | Domaine | Choix technique retenu | Solution écartée | Justification |
|---|---|---|---|---|
| D-27 | Cadre applicatif (Framework) | React (version stable courante, figée à l'installation) | Vue, Svelte | Richesse de l'écosystème, adéquation avec l'outillage et les maquettes |
| D-28 | Moteur de construction (Build) | Vite | Create React App, Next.js | Rapidité d'exécution, compilation optimisée, pas de rendu serveur requis |
| D-29 | Langage de programmation | TypeScript en mode strict | JavaScript | Sécurité de typage, détection des ruptures de contrat à la compilation |
| D-30 | Routage applicatif | React Router (mode bibliothèque avec routes imbriquées) | TanStack Router | Simplicité, maturité, adéquation parfaite avec la structure à routes parent-enfant |
| D-31 | Gestion d'état serveur | TanStack Query | Redux, Zustand | Traitement robuste du cache, détection native des états, gestion du polling |
| D-32 | Gestion d'état d'interface | Hooks natifs React (useState, useReducer) | Redux, Zustand | Suffisant pour l'état d'interface local ; aucun état global métier côté client |
| D-33 | Typage du contrat d'API | openapi-typescript et client openapi-fetch | Typage manuel | Détection des régressions dès la compilation en cas d'évolution du schéma |
| D-34 | Gestion et validation formulaires | React Hook Form associé à Zod | Formulaires contrôlés | Performance de saisie, découplage des schémas de validation réutilisables |
| D-35 | Moteur de style | Tailwind CSS avec thème mappé sur les jetons | Modules CSS, Styled-Components | Zéro surcharge d'exécution, cohérence stricte avec les jetons de design |
| D-36 | Bibliothèque de composants | shadcn/ui (composants copiés basés sur Radix UI) | Composants fermés (MUI, AntD) | Maîtrise totale du code source, accessibilité native des primitives Radix |
| D-37 | Système d'icônes | lucide-react | Icônes propriétaires | Légèreté, compatibilité directe avec les primitives shadcn/ui |
| D-38 | Gestion des transferts lourds | Module d'encapsulation XMLHttpRequest | fetch standard | Mesure précise et temps réel de la progression d'envoi de fichiers |
| D-39 | Tests unitaires et composants | Vitest associé à Testing Library | Jest | Intégration transparente et rapide avec le serveur Vite |
| D-40 | Tests de bout en bout (E2E) | Playwright | Cypress | Rapidité d'exécution, prise en charge multi-navigateurs native |
| D-41 | Qualité et formattage | ESLint et Prettier | Biome | Standards éprouvés assurant une discipline stricte sur le code |
| D-42 | Mode de déploiement | Hébergement statique (Vercel, Netlify ou Nginx) | Serveur Node.js dédié | Le front-end constitue un assemblage d'artefacts purement statiques |
| D-43 | Sécurisation de l'authentification (révisée) | Jeton d'accès Bearer en mémoire vive (sans aucun stockage dans localStorage ni sessionStorage, sans cookie pour les requêtes) et refresh token sous cookie httpOnly inaccessible au client (sans vulnérabilité CSRF par vérification d'origine) | Stockage dans localStorage ou sessionStorage | Protection renforcée contre XSS : aucun jeton persistant dans localStorage ni sessionStorage |

---

## 2. Charte graphique stricte à cinq couleurs

L'interface graphique d'IRYX applique une politique de couleur rigoureuse et fermée. Seules **cinq couleurs uniques** sont autorisées sur l'ensemble de l'application :

1. **Ink (`#020C0C`)** : Couleur de fond de page et de base sombre ; utilisée pour le texte inversé sur fond clair.
2. **Deep (`#19595A`)** : Utilisée pour les bordures, séparateurs, survol et sélections d'éléments.
3. **Teal (`#019F9E`)** : Utilisée pour le texte secondaire et les éléments d'état neutres.
4. **Cyan (`#01DBDC`)** : Utilisée pour les actions principales, les états de focus, les éléments actifs et les alertes d'importance haute.
5. **Mist (`#B7DFDF`)** : Utilisée pour le texte principal et le fond du conteneur de prévisualisation de rapport.

### 2.1 Règles impératives de contraste et d'usage des couleurs
- Sont formellement interdits dans l'ensemble des fichiers de style et de balisage : le blanc pur, le noir pur, l'orange, le rouge, le jaune, le vert ou toute nuance dérivée.
- Le texte principal repose exclusivement sur la paire `mist` sur fond `ink` (ratio de contraste élevé de 13.80).
- La couleur `deep` (`#19595A`) ne doit **jamais** être utilisée comme couleur de texte sur fond `ink`, en raison d'un contraste insuffisant (ratio de 2.47).
- Le texte `cyan` sur fond `teal` ou `mist` est formellement interdit (contraste insuffisant).
- Aucune transparence ou opacité n'est admise pour créer artificiellement une nuance intermédiaire absente de la palette.

### 2.2 Règles de restitution des sévérités et alertes
- **Règle absolue d'accessibilité** : Une sévérité, un état d'erreur ou une criticité ne doit **jamais** être signalée par la couleur seule.
- Toute indication de niveau de sévérité ou d'alerte associe impérativement :
  - Un libellé textuel explicite en lettres majuscules (ex. « ÉLEVÉE », « MOYENNE », « FAIBLE », « VALIDÉ », « ÉCHEC »).
  - Une icône figurative dédiée issue de lucide-react (ex. triangle d'alerte, coche, croix, bouclier).
  - Un traitement graphique conforme à la palette :
    - Sévérité haute / échec : fond plein cyan avec texte ink et icône associée.
    - Sévérité moyenne : contour cyan de deux pixels, texte cyan et libellé associé.
    - Sévérité faible : contour deep, texte teal et libellé associé.
    - État validé : fond mist, texte ink, icône de coche et libellé associé.

---

## 3. Structure de l'arborescence du code source

L'arborescence du répertoire `frontend/` est organisée de manière modulaire sans dépendance circulaire :

- `frontend/`
  - `src/`
    - `app/` : Point d'entrée de l'application, instanciation du routeur et des fournisseurs globaux (TanStack Query, gestionnaire de notifications).
    - `pages/` : Modules de premier niveau correspondant exactement aux écrans répertoriés dans la cartographie des routes.
    - `features/` : Découpage par domaine fonctionnel (cases, evidence, investigation, results, review, report) regroupant les composants spécialisés, les hooks d'appels API et les schémas de formulaire Zod.
    - `components/` : Composants génériques réutilisables issus de shadcn/ui et composants communs propres à l'identité visuelle d'IRYX.
    - `api/` : Couche d'accès HTTP comprenant les types générés automatiquement depuis le contrat OpenAPI, le client openapi-fetch et le gestionnaire de téléversement XMLHttpRequest.
    - `lib/` : Fonctions utilitaires pures (formatage des dates en UTC, tronquage sécurisé d'empreintes SHA-256).
    - `styles/` : Fichiers de configuration de Tailwind, définition des classes de jetons et règles de styles globales.
    - `test/` : Utilitaires et environnements de tests unitaires et d'intégration.
  - `e2e/` : Scénarios de validation de bout en bout exécutés via Playwright.
  - `public/` : Ressources graphiques statiques (favicon, logo vectoriel conforme).

### 3.1 Règles de dépendances strictes entre dossiers
1. Le dossier `pages` est habilité à importer les modules situés dans `features`, `components`, `api` et `lib`.
2. Le dossier `features` ne doit en aucun cas importer d'éléments situés dans `pages`.
3. Le dossier `components` regroupe des composants de présentation purs et ne doit importer ni `features`, ni `api`.
4. Le dossier `lib` rassemble du code utilitaire exempt de dépendance visuelle et ne doit importer aucun composant.

---

## 4. Règles de conception des composants

1. **Découplage des requêtes réseau** : Aucun composant de présentation ou de formulaire n'exécute directement d'appel d'API. Tous les échanges réseau transitent exclusivement par des hooks TanStack Query encapsulés dans le dossier `features`.
2. **Gestion de session et démarrage** : La route initiale d'entrée est `/login`, qui redirige vers `/cases` dès validation de la session.
3. **Absence totale de secrets** : Aucun mot de passe, secret de hachage, clé d'API ou URL absolue d'infrastructure de production ne doit être inscrit dans les fichiers sources du front-end.
4. **Langue unique** : Tous les textes affichés à l'écran, infobulles, alertes et messages d'erreurs techniques sont rédigés en langue française.

---

## 5. Modalités de build des stories et isolation du suivi

1. **Non-utilisation de bmad-build pour le front-end** : Le build des stories front-end ne passe PAS par `bmad-build` tant que celui-ci met à jour le fichier `sprint-status.yaml` du back-end.
2. **Sessions de développement dédiées** : Les stories front-end seront construites par session dédiée, avec la spécification technique en entrée et le suivi manuel en sortie (`frontend-sprint-status.yaml`).
3. **Règle d'or d'isolation du suivi back-end** : Aucune session front-end n'écrit dans `_bmad-output/implementation-artifacts/sprint-status.yaml`.

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-25
