import pytest
import asyncio
import os
import json
from intelligence_engine.core.optimizations import (
    LazyLoader,
    async_wrap,
    content_hash_cache,
    async_content_hash_cache,
    wrap_llm_with_router,
    CACHE_DIR
)

# 1. Test LazyLoader
def test_lazy_loader():
    loader = LazyLoader("json")
    assert loader._module is None
    # Access an attribute to trigger loading
    dumps = loader.dumps
    assert loader._module is not None
    assert dumps({"a": 1}) == '{"a": 1}'

# 2. Test async_wrap
@pytest.mark.asyncio
async def test_async_wrap():
    def sync_func(a, b):
        return a + b

    wrapped = async_wrap(sync_func)
    result = await wrapped(2, 3)
    assert result == 5

# 3. Test multi-tier caching system
def test_content_hash_cache(tmp_path):
    call_count = 0
    unique_val = os.urandom(8).hex()

    @content_hash_cache
    def expensive_func(x, u):
        nonlocal call_count
        call_count += 1
        return x * 2

    # First call
    res1 = expensive_func(10, unique_val)
    assert res1 == 20
    assert call_count == 1

    # Second call - should hit cache
    res2 = expensive_func(10, unique_val)
    assert res2 == 20
    assert call_count == 1

    # Different arg - cache miss
    res3 = expensive_func(20, unique_val)
    assert res3 == 40
    assert call_count == 2

@pytest.mark.asyncio
async def test_async_content_hash_cache():
    call_count = 0
    unique_val = os.urandom(8).hex()

    @async_content_hash_cache
    async def async_expensive_func(x, u):
        nonlocal call_count
        call_count += 1
        return x * 2

    # First call
    res1 = await async_expensive_func(100, unique_val)
    assert res1 == 200
    assert call_count == 1

    # Second call
    res2 = await async_expensive_func(100, unique_val)
    assert res2 == 200
    assert call_count == 1

# 5. Test Auto Model Router
def test_wrap_llm_with_router():
    class DummyLLM:
        def invoke(self, messages, *args, **kwargs):
            return "heavy response"
        async def ainvoke(self, messages, *args, **kwargs):
            return "heavy async response"
            
    llm = DummyLLM()
    wrapped_llm = wrap_llm_with_router(llm)
    
    # Test short message without 'explain'
    res = wrapped_llm.invoke("hello")
    assert hasattr(res, 'content')
    assert "Lightweight model response" in res.content
    
    # Test short message with 'explain'
    res2 = wrapped_llm.invoke("please explain this")
    assert res2 == "heavy response"
    
    # Test long message
    long_msg = "a" * 201
    res3 = wrapped_llm.invoke(long_msg)
    assert res3 == "heavy response"

@pytest.mark.asyncio
async def test_wrap_llm_with_router_async():
    class DummyLLM:
        def invoke(self, messages, *args, **kwargs):
            return "heavy response"
        async def ainvoke(self, messages, *args, **kwargs):
            return "heavy async response"
            
    llm = DummyLLM()
    wrapped_llm = wrap_llm_with_router(llm)
    
    # Test short message without 'explain'
    res = await wrapped_llm.ainvoke("hello")
    assert hasattr(res, 'content')
    assert "Lightweight model response" in res.content
    
    # Test short message with 'explain'
    res2 = await wrapped_llm.ainvoke("please explain this")
    assert res2 == "heavy async response"
    
    # Test long message
    long_msg = "a" * 201
    res3 = await wrapped_llm.ainvoke(long_msg)
    assert res3 == "heavy async response"
