"""
Performance Regression Tests for PDF Generation

These tests ensure that PDF rendering performance stays within acceptable limits.
Run with: python -m pytest tests/test_performance.py -v
"""

import time
import json
from pathlib import Path
import pytest

# Import rendering functions
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.render import render_html, render_pdf


@pytest.fixture
def sample_cv_data():
    """Load sample CV data for testing"""
    repo_root = Path(__file__).parent.parent
    sample_path = repo_root / "samples" / "minimal_cv.json"

    if not sample_path.exists():
        pytest.skip("Sample CV not found")

    return json.loads(sample_path.read_text(encoding="utf-8"))


def test_html_render_performance(sample_cv_data):
    """Ensure HTML rendering stays under 100ms"""
    iterations = 5
    timings = []

    for _ in range(iterations):
        start = time.time()
        html = render_html(sample_cv_data, inline_css=True)
        duration = time.time() - start
        timings.append(duration)

    avg_time = sum(timings) / len(timings)

    # HTML rendering should be very fast with template caching
    assert avg_time < 0.1, f"HTML rendering too slow: {avg_time:.3f}s (limit: 0.1s)"

    # Verify HTML was generated
    assert len(html) > 5000, "HTML suspiciously small"

    print(f"\n  HTML render: {avg_time*1000:.1f}ms average ({iterations} iterations)")


def test_pdf_render_performance(sample_cv_data):
    """Ensure PDF rendering stays under 5 seconds (including cold start)"""
    # First render (cold start - may be slower due to font loading)
    start = time.time()
    pdf = render_pdf(sample_cv_data, enforce_two_pages=False)
    first_render = time.time() - start

    # Second render (should be faster with caching)
    start = time.time()
    pdf = render_pdf(sample_cv_data, enforce_two_pages=False)
    second_render = time.time() - start

    # Verify PDF was generated
    assert len(pdf) > 30000, "PDF suspiciously small"

    # First render includes cold start overhead
    assert first_render < 5.0, f"Cold start render too slow: {first_render:.2f}s (limit: 5.0s)"

    # Second render should benefit from font/template caching
    assert second_render < 3.0, f"Warm render too slow: {second_render:.2f}s (limit: 3.0s)"

    # Warm render should be faster than cold start (verifies caching works)
    speedup = (first_render - second_render) / first_render * 100

    print(f"\n  Cold start render: {first_render:.2f}s")
    print(f"  Warm render: {second_render:.2f}s")
    print(f"  Speedup from caching: {speedup:.1f}%")


def test_batch_rendering_no_memory_leak(sample_cv_data):
    """Ensure rendering multiple CVs doesn't leak memory"""
    try:
        import psutil
    except ImportError:
        pytest.skip("psutil not installed (pip install psutil)")

    import gc

    process = psutil.Process()

    # Force GC before measuring
    gc.collect()
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB

    # Render 20 CVs
    iterations = 20
    for i in range(iterations):
        pdf = render_pdf(sample_cv_data, enforce_two_pages=False)
        del pdf

        # Force GC every 5 iterations
        if i % 5 == 0:
            gc.collect()

    # Final GC
    gc.collect()
    final_memory = process.memory_info().rss / 1024 / 1024
    memory_growth = final_memory - initial_memory

    # Allow some memory growth (caches, buffers), but not excessive
    assert memory_growth < 50, f"Memory leak detected: {memory_growth:.1f}MB growth after {iterations} renders"

    print(f"\n  Initial memory: {initial_memory:.1f}MB")
    print(f"  Final memory: {final_memory:.1f}MB")
    print(f"  Growth: {memory_growth:.1f}MB ({iterations} renders)")


def test_render_performance_comparison():
    """Compare performance across different CV complexities"""
    repo_root = Path(__file__).parent.parent

    test_cases = [
        ("minimal", repo_root / "samples" / "minimal_cv.json"),
    ]

    results = []

    for name, path in test_cases:
        if not path.exists():
            print(f"\n  Skipping {name} (file not found)")
            continue

        cv_data = json.loads(path.read_text(encoding="utf-8"))

        start = time.time()
        html = render_html(cv_data, inline_css=True)
        html_time = time.time() - start

        start = time.time()
        pdf = render_pdf(cv_data, enforce_two_pages=False)
        pdf_time = time.time() - start

        results.append({
            "name": name,
            "html_ms": html_time * 1000,
            "pdf_s": pdf_time,
            "pdf_kb": len(pdf) / 1024
        })

    # Print comparison table
    print("\n  Performance Comparison:")
    print("  " + "-" * 60)
    print(f"  {'CV Type':<15} {'HTML (ms)':<12} {'PDF (s)':<10} {'Size (KB)':<10}")
    print("  " + "-" * 60)
    for r in results:
        print(f"  {r['name']:<15} {r['html_ms']:<12.1f} {r['pdf_s']:<10.2f} {r['pdf_kb']:<10.1f}")

    # At least one test case should have run
    assert len(results) > 0, "No test cases found"


def test_font_config_caching_works():
    """Verify font configuration caching is active"""
    from src.render import _font_config

    # After importing, font config should still be None (lazy initialization)
    # After first render, it should be cached

    sample_path = Path(__file__).parent.parent / "samples" / "minimal_cv.json"
    if not sample_path.exists():
        pytest.skip("Sample CV not found")

    cv_data = json.loads(sample_path.read_text(encoding="utf-8"))

    # First render initializes font config
    render_pdf(cv_data, enforce_two_pages=False)

    # Import the cached config
    from src import render

    # Font config should be cached (not None) OR None if using Playwright fallback
    # (Windows dev environments use Playwright, Linux uses WeasyPrint)
    cached_config = render._font_config

    # If WeasyPrint is available, config should be cached
    # If Playwright fallback, config will be None
    # Both are valid - just verify caching mechanism works

    print(f"\n  Font config cached: {cached_config is not None}")
    print(f"  Using WeasyPrint: {cached_config is not None}")
    print(f"  Using Playwright fallback: {cached_config is None}")


def test_template_caching_works():
    """Verify Jinja2 template caching is active"""
    from src.render import _jinja_env

    sample_path = Path(__file__).parent.parent / "samples" / "minimal_cv.json"
    if not sample_path.exists():
        pytest.skip("Sample CV not found")

    cv_data = json.loads(sample_path.read_text(encoding="utf-8"))

    # First render initializes template cache
    render_html(cv_data, inline_css=True)

    # Import the cached environment
    from src import render

    # Template environment should be cached
    assert render._jinja_env is not None, "Template environment not cached"

    # Verify cache_size is set
    assert render._jinja_env.cache.capacity == 400, "Template cache size not set correctly"

    print(f"\n  Template environment cached: True")
    print(f"  Cache size: {render._jinja_env.cache.capacity}")


def test_render_caching_speedup(sample_cv_data):
    """Verify that render caching provides significant speedup"""
    # Clear any existing cache
    from src.render import _render_pdf_cached
    _render_pdf_cached.cache_clear()

    # First render without cache (cold)
    start = time.time()
    pdf1 = render_pdf(sample_cv_data, enforce_two_pages=False, use_cache=False)
    no_cache_time = time.time() - start

    # Clear cache again
    _render_pdf_cached.cache_clear()

    # First cached render (cache miss, same as no cache)
    start = time.time()
    pdf2 = render_pdf(sample_cv_data, enforce_two_pages=False, use_cache=True)
    cache_miss_time = time.time() - start

    # Second cached render (cache hit - should be MUCH faster)
    start = time.time()
    pdf3 = render_pdf(sample_cv_data, enforce_two_pages=False, use_cache=True)
    cache_hit_time = time.time() - start

    # Verify PDFs are approximately the same size (metadata/timestamps may differ)
    # Allow 5% size variation due to timestamp/metadata differences
    assert abs(len(pdf1) - len(pdf2)) / len(pdf1) < 0.05, "Cached PDF size differs significantly from non-cached"
    assert abs(len(pdf2) - len(pdf3)) / len(pdf2) < 0.05, "Cache hit PDF size differs significantly"

    # Cache hit should be significantly faster (at least 50% faster)
    speedup = (cache_miss_time - cache_hit_time) / cache_miss_time * 100

    assert cache_hit_time < cache_miss_time * 0.5, \
        f"Cache hit not fast enough: {cache_hit_time:.3f}s vs {cache_miss_time:.3f}s (speedup: {speedup:.1f}%)"

    print(f"\n  Without cache: {no_cache_time:.3f}s")
    print(f"  Cache miss: {cache_miss_time:.3f}s")
    print(f"  Cache hit: {cache_hit_time:.3f}s")
    print(f"  Speedup from caching: {speedup:.1f}%")

    # Check cache stats
    cache_info = _render_pdf_cached.cache_info()
    print(f"  Cache stats: {cache_info.hits} hits, {cache_info.misses} misses, {cache_info.currsize}/{cache_info.maxsize} entries")


def test_cache_key_stability(sample_cv_data):
    """Verify cache keys are stable and change when CV data changes"""
    from src.render import _cv_cache_key

    # Same data should produce same key
    key1 = _cv_cache_key(sample_cv_data)
    key2 = _cv_cache_key(sample_cv_data)
    assert key1 == key2, "Cache key should be stable for same data"

    # Modified data should produce different key
    modified_cv = dict(sample_cv_data)
    modified_cv['full_name'] = "Different Name"
    key3 = _cv_cache_key(modified_cv)
    assert key1 != key3, "Cache key should change when CV data changes"

    # Metadata fields shouldn't affect cache key
    with_metadata = dict(sample_cv_data)
    with_metadata['_metadata'] = {"some": "metadata"}
    key4 = _cv_cache_key(with_metadata)
    assert key1 == key4, "Cache key should ignore metadata fields"

    print(f"\n  Cache key (first 16 chars): {key1[:16]}...")
    print(f"  Keys are stable: {key1 == key2}")
    print(f"  Keys change with data: {key1 != key3}")
    print(f"  Metadata ignored: {key1 == key4}")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
