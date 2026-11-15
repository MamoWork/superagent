def test_opportunity_core_is_the_same_contract():
    from app.schemas import Signal as AppSignal
    from opportunity_core import Signal as CoreSignal
    from app.providers.base import SourceProvider as AppProvider
    from opportunity_core.providers.base import SourceProvider as CoreProvider

    assert AppSignal is CoreSignal
    assert AppProvider is CoreProvider
