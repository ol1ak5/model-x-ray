import pytest

from model_x_ray import llm as llm_module
from model_x_ray.llm import ROLE_MODELS, build_chat_model, model_for_role


def test_the_role_registry_maps_roles_to_models_and_overrides_from_the_environment(monkeypatch) -> None:
    monkeypatch.setattr(llm_module, "load_dotenv", lambda: None)
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.setenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
    for role in ROLE_MODELS:
        monkeypatch.delenv(f"NEBIUS_MODEL_{role.upper()}", raising=False)

    investigator = build_chat_model(role="investigator")
    assert investigator.model_name == "nvidia/nemotron-3-super-120b-a12b"
    assert investigator.request_timeout == 120.0
    assert investigator.max_retries == 3
    assert model_for_role("verifier") == "nvidia/nemotron-3-super-120b-a12b"
    assert model_for_role("mapper") == "nvidia/nemotron-3-super-120b-a12b"

    explainer = build_chat_model(role="explain")
    assert explainer.model_name == "nvidia/Nemotron-3_5-Lightning"
    assert explainer.max_tokens == 900
    assert investigator.max_tokens is None

    monkeypatch.setenv("NEBIUS_MODEL_INVESTIGATOR", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")
    assert build_chat_model(role="investigator").model_name == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"

    assert build_chat_model("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B").model_name == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"

    with pytest.raises(ValueError, match="Unknown role"):
        model_for_role("judge")
    with pytest.raises(ValueError, match="model id or a role"):
        build_chat_model()

    monkeypatch.delenv("NEBIUS_API_KEY")
    with pytest.raises(ValueError, match="NEBIUS_API_KEY"):
        build_chat_model(role="verifier")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    monkeypatch.delenv("NEBIUS_BASE_URL")
    with pytest.raises(ValueError, match="NEBIUS_BASE_URL"):
        build_chat_model(role="verifier")
