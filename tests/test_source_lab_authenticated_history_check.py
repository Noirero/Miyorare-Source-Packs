from pathlib import Path


WORKFLOW = Path('.github/workflows/source-lab-run-farm.yml')


def test_locked_candidate_history_check_is_authenticated_and_fail_closed():
    text = WORKFLOW.read_text(encoding='utf-8')

    assert "token = os.environ.get('GH_TOKEN')" in text
    assert "authenticated GitHub token is required for locked candidate verification" in text
    assert "'Authorization': f'Bearer {token}'" in text
    assert "'X-GitHub-Api-Version': '2022-11-28'" in text


def test_isolated_child_plan_step_receives_ephemeral_github_token_without_persisting_secret():
    text = WORKFLOW.read_text(encoding='utf-8')

    assert "github_token_expression = '$' + '{{ github.token }}'" in text
    assert 'GH_TOKEN: " + github_token_expression' in text
    assert 'git -C intake-branch add .github/workflows/upstream-sync.yml' in text
    assert 'Authorization: Bearer ' not in text
