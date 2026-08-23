# Bruno Prototype - BRU-3444 & BRU-3448 Implementation

This prototype implements the requirements from JIRA tickets BRU-3444 and BRU-3448:

## BRU-3444: Internal Events for Cache Handling Delegation

- Implemented internal event system in `src/snapshots.js`
- Added event listeners for `clear-cache-request` and `app-quit` events
- Cache clearing operations are delegated to snapshot system via internal events
- Event-driven architecture allows clean separation of concerns

## BRU-3448: Environment Path Re-serialization

- Added re-serialization logic in `src/collections.js` for non-mounted collections
- `reSerializeEnvironmentPath()` function ensures proper environment path handling
- Normalizes paths across platforms (Windows/Linux/macOS)
- Adds serialization metadata for tracking

## Architecture

- `src/main.js`: Main entry point and coordination
- `src/snapshots.js`: Internal event system and cache delegation
- `src/cache.js`: Cache management with event-triggered clearing
- `src/collections.js`: Collection restoration with environment re-serialization
- `src/index.js`: Application initialization and integration

## Usage

```bash
npm install
npm start
```

The implementation follows Bruno's architecture patterns while addressing the specific requirements of the JIRA tickets.