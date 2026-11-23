# 08 - Architecture Back-End : Référence Complète

Le document d'architecture back-end complet et détaillé a été produit et formellement validé dans le cadre des artefacts de solutioning BMAD.

Consulter le document maître :
- [architecture.md](../_bmad-output/planning-artifacts/architecture.md)

Il intègre sans modification :
- Les décisions **D-01 à D-26** figées
- Les décisions d'architecture **ADR-0001 à ADR-0003** et les décisions acceptées **ADR-0004 à ADR-0010** (couvrant DP-01 à DP-07)
- Les **couches logicielles** du monolithe modulaire
- Les **rôles d'agents** (Planner, Executor, Analyst, Verifier, Corrélateur, Rapporteur)
- Le **modèle de données** complet (13 entités et leurs invariants)
- Les **règles de sécurité** (isolation air-gap, non-root, portes H1/H2/H3, Presidio, audit append-only)
- Le **diagramme textuel des flux entre couches**
- La **structure complète des dossiers du back-end** et le rôle de chaque module
- **Aucune décision proposée ouverte** (l'ensemble des propositions DP-01 à DP-07 ont été arbitrées et validées par ADR)
