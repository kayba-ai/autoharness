from autoharness.autonomy import policy_for_mode


def test_proposal_mode_never_applies_patches() -> None:
    policy = policy_for_mode("proposal")
    assert policy.may_generate_proposals is True
    assert policy.may_apply_patches is False
    assert policy.allows_repo_wide_edits is False


def test_bounded_mode_requires_allowlist() -> None:
    policy = policy_for_mode("bounded", editable_surfaces=("src/agent",))
    assert policy.may_apply_patches is True
    assert policy.requires_explicit_edit_allowlist is True
    assert policy.editable_surfaces == ("src/agent",)


def test_full_mode_allows_repo_wide_edits() -> None:
    policy = policy_for_mode("full", protected_surfaces=("secrets",))
    assert policy.may_apply_patches is True
    assert policy.allows_repo_wide_edits is True
    assert policy.protected_surfaces == ("secrets",)
