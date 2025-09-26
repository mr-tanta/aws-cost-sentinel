# Contributing to AWS Cost Sentinel

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

This project follows a standard code of conduct. Please be respectful and constructive in all interactions.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Create a new branch for your feature/fix
4. Make your changes
5. Test your changes
6. Submit a pull request

## Development Setup

### Prerequisites
- Node.js 18+
- Python 3.10+
- Docker and Docker Compose
- PostgreSQL 14+
- Redis 7+

### Local Development

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/aws-cost-sentinel.git
cd aws-cost-sentinel
```

2. **Install dependencies**
```bash
# Frontend
pnpm install

# Backend
cd backend
pip install -r requirements.txt
```

3. **Start services**
```bash
# Start databases
docker-compose up postgres redis -d

# Start backend
cd backend
uvicorn app.main:app --reload

# Start frontend (new terminal)
pnpm dev
```

## Project Structure

```
aws-cost-sentinel/
├── src/                    # Next.js frontend
│   ├── app/               # App router pages
│   ├── components/        # React components
│   ├── lib/              # Utilities and API
│   └── types/            # TypeScript definitions
├── backend/               # FastAPI backend
│   └── app/
│       ├── api/          # API endpoints
│       ├── core/         # Configuration
│       ├── models/       # Data models
│       └── services/     # Business logic
├── docs/                  # Documentation
└── docker-compose.yml     # Docker configuration
```

## Making Changes

### Frontend Development
- Use TypeScript for all new code
- Follow React best practices
- Use Material-UI components when possible
- Add proper error handling
- Write responsive designs

### Backend Development
- Follow FastAPI conventions
- Use async/await for I/O operations
- Add proper error handling
- Include docstrings for functions
- Validate inputs with Pydantic models

### Database Changes
- Create migrations for schema changes
- Test migrations on sample data
- Document any breaking changes

## Code Style

### Frontend
- Use TypeScript strict mode
- Follow ESLint rules
- Use consistent naming conventions
- Keep components small and focused

### Backend
- Follow PEP 8 style guide
- Use type hints
- Keep functions focused and small
- Add proper logging

## Testing

### Frontend Tests
```bash
pnpm test
```

### Backend Tests
```bash
cd backend
pytest
```

### Integration Tests
```bash
docker-compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

## Submitting Changes

1. **Create a descriptive branch name**
   - `feature/add-budget-alerts`
   - `fix/cost-calculation-bug`
   - `docs/update-api-reference`

2. **Write clear commit messages**
   ```
   Add budget alert functionality

   - Implement alert thresholds
   - Add email notifications
   - Update dashboard UI
   ```

3. **Test your changes**
   - Run all tests locally
   - Test the feature manually
   - Check for any breaking changes

4. **Submit a pull request**
   - Use the PR template
   - Link any related issues
   - Add screenshots for UI changes

## Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests pass locally
- [ ] Manual testing completed
- [ ] No breaking changes

## Screenshots (if applicable)
Add screenshots for UI changes

## Additional Notes
Any additional context or notes
```

## Issue Guidelines

### Bug Reports
Include:
- Steps to reproduce
- Expected behavior
- Actual behavior
- Screenshots/logs
- Environment details

### Feature Requests
Include:
- Clear description
- Use case/motivation
- Proposed solution
- Alternatives considered

## Documentation

- Update documentation for any new features
- Keep README.md current
- Add API documentation for new endpoints
- Include code examples

## Release Process

1. Version bump in package.json
2. Update CHANGELOG.md
3. Tag release
4. Build and test Docker images
5. Create GitHub release

## Getting Help

- Check existing issues and discussions
- Ask questions in GitHub Discussions
- Join our community chat
- Email maintainers for security issues

## Recognition

Contributors will be:
- Added to CONTRIBUTORS.md
- Mentioned in release notes
- Recognized in project documentation

Thank you for contributing to AWS Cost Sentinel!