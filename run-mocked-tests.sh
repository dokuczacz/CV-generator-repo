#!/bin/bash

# Test runner for mocked OpenAI CV generator workflow
# Runs Playwright tests that walk through the full CV generation UI without calling OpenAI

echo "========================================="
echo "CV Generator - Mocked AI E2E Tests"
echo "========================================="
echo ""

# Check prerequisites
if ! command -v npm &> /dev/null; then
    echo "❌ npm not found. Please install Node.js first."
    exit 1
fi

if ! command -v func &> /dev/null; then
    echo "⚠️  Azure Functions CLI not found. Make sure local backend is running:"
    echo "   cd . && func start"
    exit 1
fi

echo "Prerequisites: ✅"
echo ""

# Ensure frontend dependencies are installed
if [ ! -d "ui/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd ui && npm install && cd ..
    echo "Frontend ready: ✅"
else
    echo "Frontend dependencies: ✅"
fi

# Check if backend is running
echo ""
echo "Checking backend health..."
if curl -s http://localhost:7071/api/health > /dev/null 2>&1; then
    echo "Backend (localhost:7071): ✅"
else
    echo "⚠️  Backend not responding at localhost:7071"
    echo "   Make sure to run: func start (in another terminal)"
fi

echo ""
echo "Checking frontend..."
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo "Frontend (localhost:3000): ✅"
else
    echo "⚠️  Frontend not running at localhost:3000"
    echo "   Make sure to run: npm run dev (in another terminal, from ui/)"
fi

echo ""
echo "========================================="
echo "Running mocked E2E tests..."
echo "========================================="
echo ""

# Run the specific mocked test file
npm test -- tests/e2e/cv-generator-mocked.spec.ts

echo ""
echo "========================================="
echo "Test Summary:"
echo "========================================="
echo "✅ = UI stage rendered correctly"
echo "🔄 = Mocked OpenAI response used (no real API calls)"
echo "📊 = Final PDF generated"
echo ""
echo "Test artifacts saved to: tests/test-output/"
echo "========================================="
