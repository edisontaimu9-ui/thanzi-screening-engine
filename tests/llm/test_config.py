"""Configuration, endpoint privacy policy and generation parameters."""
import pytest

from thanzi_screen.llm import GenerationParams, LLMConfig, LLMConfigError, Message, check_endpoint, is_local_host
from thanzi_screen.llm.errors import LLMBadRequestError
from thanzi_screen.llm.config import enabled_from_env
from thanzi_screen.llm.providers.ollama import keep_alive_value, model_listed


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]", "10.1.2.3", "192.168.0.9", "172.20.0.5",
                                  "169.254.1.1", "ollama", "llm-server", "box.lan", "svc.internal", "x.cluster.local"])
def test_local_hosts(host):
    assert is_local_host(host)


@pytest.mark.parametrize("host", ["example.com", "api.openai.com", "8.8.8.8", "1.1.1.1", "llm.example.org", ""])
def test_remote_hosts(host):
    assert not is_local_host(host)


def test_default_config_is_local_and_small():
    c = LLMConfig()
    assert c.endpoint == "http://127.0.0.1:11434" and c.max_concurrency == 1 and c.allow_remote is False
    assert c.params.max_tokens == 256 and c.params.context_tokens == 2048


@pytest.mark.parametrize("url", ["https://api.example.com", "http://example.com:8080", "http://8.8.8.8"])
def test_remote_endpoint_refused_by_default(url):
    with pytest.raises(LLMConfigError) as e:
        check_endpoint(url)
    assert "example" not in str(e.value) and "8.8.8.8" not in str(e.value)          # the URL is never echoed


def test_remote_needs_https_even_when_allowed():
    assert check_endpoint("https://llm.example.com", allow_remote=True) == "https://llm.example.com"
    with pytest.raises(LLMConfigError):
        check_endpoint("http://llm.example.com", allow_remote=True)


@pytest.mark.parametrize("url", ["ftp://127.0.0.1", "127.0.0.1:11434", "http://", "http://user:pw@127.0.0.1",
                                 "http://127.0.0.1?x=1", "http://127.0.0.1#f", "http://127.0.0.1:99999", "", "file:///etc"])
def test_malformed_or_unsafe_endpoints(url):
    with pytest.raises(LLMConfigError):
        check_endpoint(url)


def test_trailing_slash_and_prefix_are_normalised():
    assert check_endpoint("http://127.0.0.1:8080/") == "http://127.0.0.1:8080"
    assert check_endpoint("http://ollama:11434/api-prefix/") == "http://ollama:11434/api-prefix"


def test_api_key_never_in_repr_and_must_be_clean():
    c = LLMConfig(api_key="secret-value-abc")
    assert "secret-value-abc" not in repr(c) and "secret-value-abc" not in str(c)
    with pytest.raises(LLMConfigError):
        LLMConfig(api_key="bad\r\nHeader: x")


@pytest.mark.parametrize("model", ["", "bad model", "x;rm", "a" * 200, "-lead", "q\nx"])
def test_model_name_charset(model):
    with pytest.raises(LLMConfigError):
        LLMConfig(model=model)


@pytest.mark.parametrize("model", ["qwen2.5:1.5b", "qwen3:0.6b", "hf.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M", "m"])
def test_model_names_accepted(model):
    assert LLMConfig(model=model).model == model


@pytest.mark.parametrize("kwargs", [dict(connect_timeout_s=0), dict(request_timeout_s=-1), dict(request_timeout_s=10_000),
                                    dict(max_concurrency=0), dict(max_concurrency=99), dict(max_retries=9),
                                    dict(retry_backoff_s=-1), dict(keep_alive="forever"), dict(provider="Bad Name"),
                                    dict(max_response_bytes=0), dict(max_prompt_chars=0)])
def test_out_of_range_settings(kwargs):
    with pytest.raises(LLMConfigError):
        LLMConfig(**kwargs)


@pytest.mark.parametrize("value", ["0", "-1", "30s", "5m", "1.5h", "250ms"])
def test_keep_alive_accepts(value):
    assert LLMConfig(keep_alive=value).keep_alive == value


def test_keep_alive_wire_value():
    assert keep_alive_value("0") == 0 and keep_alive_value("-1") == -1 and keep_alive_value("5m") == "5m"


@pytest.mark.parametrize("kw", [dict(max_tokens=0), dict(max_tokens=99999), dict(temperature=-0.1), dict(temperature=3),
                                dict(top_p=0), dict(top_p=1.5), dict(top_k=0), dict(seed=-1), dict(context_tokens=10),
                                dict(stop=("a",) * 5), dict(stop=("",)), dict(stop=("x" * 65,))])
def test_generation_params_validate(kw):
    with pytest.raises(LLMConfigError):
        GenerationParams(**kw)


def test_params_overrides_ignore_none():
    base = GenerationParams()
    out = base.with_overrides(max_tokens=64, temperature=None)
    assert out.max_tokens == 64 and out.temperature == base.temperature and base.max_tokens == 256


def test_messages_validate():
    with pytest.raises(LLMBadRequestError):
        Message("user", "   ")
    with pytest.raises(LLMBadRequestError):
        Message("tool", "x")                                  # type: ignore[arg-type]


def test_from_env_reads_everything_and_names_bad_variables():
    env = {"THANZI_LLM_PROVIDER": "LlamaCpp", "THANZI_LLM_ENDPOINT": "http://llm:8080", "THANZI_LLM_MODEL": "qwen3:1.7b",
           "THANZI_LLM_TIMEOUT_S": "30", "THANZI_LLM_MAX_CONCURRENCY": "2", "THANZI_LLM_THINK": "false",
           "THANZI_LLM_MAX_TOKENS": "128", "THANZI_LLM_TEMPERATURE": "0.1", "THANZI_LLM_KEEP_ALIVE": "0",
           "THANZI_LLM_API_KEY": "k" * 20}
    c = LLMConfig.from_env(env)
    assert (c.provider, c.endpoint, c.model, c.request_timeout_s, c.max_concurrency, c.think) == \
           ("llamacpp", "http://llm:8080", "qwen3:1.7b", 30.0, 2, False)
    assert c.params.max_tokens == 128 and c.params.temperature == 0.1 and c.keep_alive == "0" and c.api_key == "k" * 20
    with pytest.raises(LLMConfigError) as e:
        LLMConfig.from_env({"THANZI_LLM_TIMEOUT_S": "soon-ish"})
    assert "THANZI_LLM_TIMEOUT_S" in str(e.value) and "soon-ish" not in str(e.value)
    with pytest.raises(LLMConfigError):
        LLMConfig.from_env({"THANZI_LLM_THINK": "maybe"})


def test_from_env_empty_gives_defaults():
    assert LLMConfig.from_env({}) == LLMConfig()


def test_from_mapping_rejects_unknown_keys_and_wrong_types():
    with pytest.raises(LLMConfigError):
        LLMConfig.from_mapping({"modle": "x"})
    with pytest.raises(LLMConfigError):
        LLMConfig.from_mapping({"stop": 5})
    c = LLMConfig.from_mapping({"model": "qwen2.5:0.5b", "params": {"max_tokens": 32}, "temperature": 0.5, "stop": ["###"]})
    assert c.params.max_tokens == 32 and c.params.temperature == 0.5 and c.params.stop == ("###",)


def test_enabled_flag_is_exactly_one():
    assert enabled_from_env({"THANZI_LLM_ENABLED": "1"})
    assert not enabled_from_env({}) and not enabled_from_env({"THANZI_LLM_ENABLED": "true"})


def test_model_listing_handles_latest_tag():
    assert model_listed("llama3", ["llama3:latest"]) and model_listed("qwen2.5:1.5b", ["qwen2.5:1.5b"])
    assert not model_listed("qwen2.5:1.5b", ["qwen2.5:0.5b"]) and not model_listed("qwen2.5", ["qwen2.5:0.5b"])
