# Troubleshooting

Common issues and solutions for the CV Generator project.

## "Cannot find module" in Next.js

```bash
cd ui && rm -rf node_modules package-lock.json
npm install
```

## Azure Functions not starting

Check Python version (must be 3.11):
```bash
python --version
```

Reinstall dependencies:
```bash
pip install -r requirements.txt --force-reinstall
```

## Tests failing

Regenerate test artifacts:
```bash
npm run pretest
```

Run headed to debug:
```bash
npm run test:headed
```

## Photo extraction fails

Verify DOCX structure:
```bash
python -c "from docx import Document; doc = Document('sample.docx'); print([r._element.xml for r in doc.part.rels.values()])"
```

## Azure Table Storage Limits

- Property size: 64KB max
- Photo URLs must be <32KB (base64-encoded)
- Use blob storage for large data

## WeasyPrint CSS Quirks

- Limited CSS support (no Grid, limited Flexbox)
- Use float-based layouts for compatibility
- Test across template languages (EN/DE/PL)

## Playwright Visual Regression

- Baselines stored in `test-results/`
- Update baselines intentionally: `npm test -- --update-snapshots`
- 5% diff threshold (configurable in `playwright.config.ts`)