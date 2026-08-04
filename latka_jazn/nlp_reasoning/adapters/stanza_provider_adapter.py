from __future__ import annotations

from pathlib import Path

from latka_jazn.nlp.local_resource_paths import installed_provider_names, stanza_model_dir
from latka_jazn.nlp.providers.optional_stanza_provider import OptionalStanzaPolishProvider
from latka_jazn.nlp_reasoning.models import MorphCandidate, ProviderStatus


class StanzaReasoningAdapter:
    """Expose the existing Stanza provider through the reasoning-frame contract."""

    provider_name = "stanza-pl"

    def __init__(
        self,
        *,
        root: str | Path | None = None,
        provider: OptionalStanzaPolishProvider | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else None
        installed = self.provider_name in installed_provider_names(self.root)
        self.provider = provider or OptionalStanzaPolishProvider(
            enabled=installed,
            model_dir=stanza_model_dir(self.root),
        )

    @property
    def status(self) -> ProviderStatus:
        return ProviderStatus(
            provider=self.provider_name,
            available=bool(self.provider.available),
            mode="offline" if self.provider.available else "offline_optional",
            reason=None if self.provider.available else self.provider.last_error or "stanza provider unavailable",
            license="Apache-2.0 library; downloaded model licenses are recorded in resources.json",
            source_url="https://stanfordnlp.github.io/stanza/download_models.html",
            data_path=str(self.provider.model_dir),
            dictionary="pl-ud",
        )

    def analyse(self, text: str) -> list[MorphCandidate]:
        result = self.provider.analyse_text(text, include_ner=False)
        if not result.available:
            return []
        out: list[MorphCandidate] = []
        token_index = 0
        for sentence in result.sentences:
            for word in sentence:
                surface = word.text
                lemma = word.lemma or surface
                upos = word.upos or "X"
                xpos = word.xpos or ""
                out.append(
                    MorphCandidate(
                        surface=surface,
                        lemma=lemma,
                        tag=f"{upos}:{xpos}" if xpos else upos,
                        start=token_index,
                        end=token_index + 1,
                        provider=self.provider_name,
                        confidence=0.94,
                        features={"pos": upos.lower(), **{key.lower(): value for key, value in word.feats.items()}},
                        raw={"head": word.head, "deprel": word.deprel},
                    )
                )
                token_index += 1
        return out
