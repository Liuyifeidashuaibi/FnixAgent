# Bruno WebSocket Multi-Message Feature

This implementation adds support for multiple WebSocket messages within a single request, addressing JIRA ticket BRU-2932.

## Features

- ✅ **Multiple Messages**: Add unlimited WebSocket messages to a single request
- ✅ **Collapsible Accordions**: Each message is displayed as an expandable/collapsible panel
- ✅ **Individual Message Control**: Each message has its own type selection (text/binary)
- ✅ **Message Actions**: Send, rename, and delete actions for each individual message
- ✅ **File Format Support**: Works with both BRU and YAML file formats
- ✅ **Backward Compatibility**: Seamless migration from single-message to multi-message format
- ✅ **Auto-Expand**: New messages automatically expand for immediate editing
- ✅ **Inline Editing**: Click on message names to rename them instantly

## File Format Support

### Multi-Message BRU/YAML Format
```yaml
url: wss://example.com
headers:
  Authorization: Bearer token
messages:
  - name: Hello Message
    type: text
    content: |
      Hello, World!
  - name: Binary Message
    type: binary
    content: |
      base64data==
```

### Legacy Single-Message Format (Backward Compatible)
```yaml
url: wss://example.com
headers:
  Authorization: Bearer token
message:
  type: text
  content: |
    Hello, World!
```

## Usage

1. Open a WebSocket request in Bruno
2. Click "Add Message" to create additional messages
3. Each message appears as a collapsible accordion
4. Click the message name to rename it
5. Select text or binary type for each message
6. Click "Send" to send individual messages
7. Click "×" to delete messages

## Technical Implementation

- **Models**: `src/models/websocket-message.ts` defines the data structures
- **UI Component**: `src/components/requests/WebSocketRequestEditor.tsx` implements the accordion UI
- **Serialization**: `src/utils/websocket-serializer.ts` handles BRU/YAML import/export
- **Configuration**: `src/config/websocket-config.ts` contains feature settings
- **Tests**: `src/tests/websocket-multi-message.test.ts` ensures correctness

## Contributing

This feature follows Bruno's contribution guidelines and maintains backward compatibility while adding powerful multi-message capabilities.