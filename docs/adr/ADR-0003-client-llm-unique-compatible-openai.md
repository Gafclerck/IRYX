# ADR-0003 : Client LLM unique compatible OpenAI, configuré par rôle
 
- **Date** : 2026-11-23
- **Statut** : acceptée
 
---
 
## Contexte
 
La chaîne d'agents d'IRYX implique différents rôles (Planner, Analyst, Rapporteur) ayant des exigences distinctes en matière de puissance de raisonnement, de latence et de confidentialité.
 
Il était envisageable d'intégrer des SDK propriétaires multiples (Google GenAI, Anthropic, RodiumAi SDK propriétaire, Mistral) ou d'intercaler un proxy mandataire tel que LiteLLM Proxy.
 
Cependant, l'introduction d'un proxy ou de multiples bibliothèques clientes complique le déploiement conteneurisé, accroît la surface d'attaque et fragilise le code en cas d'évolutions d'APIs.
 
---
 
## Décision
 
Nous adoptons un **module client unique basé sur le SDK officiel `openai`** (D-10) paramétrable par rôle :
1. Un seul composant client d'inférence est développé dans le back-end. Il accepte pour chaque rôle deux variables de configuration : `base_url` et `model`.
2. Les appels réseau sont protégés par la bibliothèque `tenacity` (D-11) avec stratégie de retry bornée et backoff exponentiel.
3. En phase de développement et de démonstration, le client interroge un point d'accès d'API compatible OpenAI (Groq ou RodiumAi).
4. Lors du passage en production souveraine, le basculement vers un modèle open-source Gemma auto-hébergé (ex. servi localement via vLLM ou Ollama) s'opère par simple modification des variables d'environnement `base_url` et `model`, sans aucune réécriture de code.
5. Tout envoi vers une API externe requiert obligatoirement le passage par le filtre de pseudonymisation Microsoft Presidio (D-19) et l'autorisation explicite de la porte H3.
6. L'utilisation d'un proxy intermédiaire (LiteLLM Proxy) ou de SDKs propriétaires hétérogènes est formellement rejetée.
 
---
 
## Conséquences
 
### Positives
- **Portabilité maximale** : Même code d'inférence utilisable indifféremment sur des APIs cloud tierces ou sur un modèle hébergé sur site (on-premise).
- **Zéro dépendance complexe** : Pas de proxy externe à administrer ou superviser dans Docker Compose.
- **Résilience** : Gestion centralisée et testable des timeouts et des réessais via `tenacity`.
- **Auditabilité** : Toutes les invites de commande (prompts) et réponses sont tracées de manière uniforme.
 
### Négatives / Risques
- Imposition d'une compatibilité stricte OpenAI Chat Completions sur les fournisseurs d'IA retenus (standard de facto largement supporté par l'écosystème).
 
---
 
Relecture croisée : Team Lead (Abdoul-Gafar AMADOU) & Product Lead (Abdoul-Gafar AMADOU) - 2026-11-23
