# Contributing to Bruno Scroll Position Persistence

Thank you for considering contributing to this feature! Please follow these guidelines.

## Code Style

- Follow Bruno's existing code style and conventions
- Use TypeScript for type safety
- Write descriptive commit messages
- Include tests for new functionality

## Development Setup

1. Clone the repository
2. Install dependencies: `npm install`
3. Run tests: `npm test`
4. Start development server: `npm start`

## Testing

All scroll position persistence functionality must be covered by unit tests:

```bash
npm run test:scroll
```

## Pull Request Guidelines

- Create a separate branch for your feature
- Reference the JIRA issue (BRU-3338) in your PR description
- Include screenshots or gifs if applicable
- Ensure your PR addresses only one issue or adds one feature
- Keep PRs small and focused for easier review

## Code Review Checklist

- [ ] Scroll position is persisted across tab switches
- [ ] Scroll position is restored on component mount
- [ ] localStorage persistence works correctly
- [ ] Error handling for localStorage failures
- [ ] Performance considerations addressed
- [ ] TypeScript types are complete and accurate
- [ ] Tests pass and cover edge cases

## License

By contributing, you agree that your contributions will be licensed under the MIT License.