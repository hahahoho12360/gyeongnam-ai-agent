# Personal regional records and anonymous authentication

All required data/conversation APIs remain. Date/value/memo is extended with region_id and metric_type; units come from the server CSV-metric catalog. Official statistics are never modified. Summaries group by region and metric, so different units are not averaged together. Source is user_record, not an official statistic. Old minimal API clients may use the legacy custom metric; the new UI requires a region and catalog metric.

Protected endpoints: /api/data (CRUD and summary), /api/conversations (create/list/load/delete), /api/chat. Each request requires a Firebase ID token verified by Firebase Admin with revocation checking. owner_uid always comes from the verified token; clients cannot assign it. Cross-user and ownerless document access returns 404. Ownership is checked before any AI call when continuing a conversation. Public analytics, exports, metric definitions, health and Swagger remain public. No production bypass exists. Only tests override the authentication dependency.

## Required configuration before private functionality works

1. Firebase Console → Authentication → Sign-in method → Anonymous → Enable and save.
2. Project settings → General → Your apps → existing/new Web app → SDK configuration. Copy only apiKey, projectId and authDomain. The web apiKey identifies the Firebase project; it is intentionally public and must never be replaced with the data.go.kr key or service-account JSON.
3. Render service → Environment: set FIREBASE_WEB_API_KEY to the Web app apiKey. Existing FIREBASE_PROJECT_ID must match the Web app. Optional FIREBASE_AUTH_DOMAIN from the Web config (otherwise projectId.firebaseapp.com). Save and deploy. Service-account secrets remain server-side.
4. Authentication settings → Authorized domains: add gyeongnam-ai-agent.vercel.app (and an explicitly used custom frontend domain). Enable Anonymous and use matching project configuration.
5. Firestore Rules: browser access should be denied because this app uses the server API. Review/apply the supplied firestore.rules in this dedicated project. A permissive wildcard rule would still allow bypassing server ownership checks; endpoint tests alone cannot certify the console rules. Admin SDK/API and collection Actions continue operating under server IAM.
6. Reload the frontend or use Reconnect. Auth config errors leave private functionality disabled; public statistical lookup remains available. Do not disable API authentication to bypass configuration.

Anonymous records belong to the current browser identity. Clearing browser storage, private browsing, another browser/device or automatic anonymous-account deletion can lose access to that identity. Do not enable automatic anonymous-user cleanup if records must persist. Legacy ownerless records are hidden and preserved, never assigned to first visitors. Migrate only after ownership can be established with administrator review; this deployment performs no migration or deletion.

Verification: use two fresh browser profiles A/B; add distinct records and conversations; B must not list/load/edit/delete A's documents. Swagger requires Authorize with the Firebase ID token for private endpoints. Tokens must never be committed, shared or saved in screenshots. CI tests use synthetic identities/tokens and do not access real Firebase.

This implements per-user privacy, not email recovery/cross-device synchronization or comprehensive abuse throttling. Personal inputs are sent to the AI provider when the user selects personal analysis; no password or auth token enters the AI prompt.
