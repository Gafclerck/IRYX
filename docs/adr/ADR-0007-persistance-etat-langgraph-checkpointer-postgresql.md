# ADR-0007 : Persistance transactionnelle d'état LangGraph via Checkpointer PostgreSQL

- **Date** : 2026-11-23
- **Statut** : acceptée

---

## Contexte

La décision D-09 acte le choix de `LangGraph` pour l'orchestration du cycle d'investigation et impose la capacité d'interruption et de reprise sur incident (FR21, NFR-REL-01), ainsi que les points d'arrêt obligatoires sur les portes de contrôle humain (H1, H2, H3).

Pour persister l'état des nœuds, des canaux et des mémoires de graphe de manière transactionnelle et résiliente, un mécanisme de point de contrôle (*Checkpointer*) doit être désigné.

---

## Décision

Nous retenons l'**Option A** :
1. Utilisation du composant checkpointer officiel asynchrone `AsyncPostgresSaver` de l'écosystème LangGraph (`langgraph-checkpoint-postgres` ou sous-module Postgres officiel).
2. L'état complet de la machine d'états d'investigation est persisté directement dans l'instance PostgreSQL 16 (D-05), assurant l'unicité de la source de vérité.
3. Les transitions de phases et les statuts haut niveau restent simultanément synchronisés dans les tables relationnelles `InvestigationRun` et `InvestigationPhase` via SQLAlchemy 2.x (D-06).
4. En cas d'arrêt sur porte humaine ou d'interruption imprévue (redémarrage du worker), l'enquête peut reprendre exactement au dernier nœud validé sans recalcul.

---

## Conséquences

### Positives
- **Reproductibilité et résilience totale** : Aucun état d'agent n'est perdu lors d'un crash conteneur.
- **Composant officiel pérenne** : Évite le développement et la maintenance d'une sérialisation manuelle sur mesure fragile.
- **Support natif du Human-in-the-Loop** : Les portes H1, H2 et H3 suspendent nativement le graphe en attente de l'action de l'analyste.

### Négatives / Risques
- Génère des tables techniques internes gérées par le checkpointer de LangGraph au sein de PostgreSQL.

---

Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & AI/Tech Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
