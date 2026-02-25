"""GitHub webhook receiver and event parsing."""
import hashlib
import hmac


def verify_github_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature (SHA-256)."""
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_github_event(event_type: str, payload: dict) -> list[dict]:
    """Parse a GitHub webhook payload into normalized event dicts.

    Returns a list because push events can contain multiple commits.
    """
    repo = payload.get("repository", {}).get("full_name", "")

    if event_type == "push":
        return _parse_push(payload, repo)
    elif event_type == "pull_request":
        return _parse_pull_request(payload, repo)
    elif event_type == "pull_request_review":
        return _parse_pr_review(payload, repo)
    elif event_type == "issue_comment":
        return _parse_issue_comment(payload, repo)
    else:
        return []


def _parse_push(payload: dict, repo: str) -> list[dict]:
    events = []
    for commit in payload.get("commits", []):
        events.append({
            "source": "github",
            "source_id": commit["id"],
            "event_type": "push",
            "actor_email": commit.get("author", {}).get("email"),
            "actor_name": commit.get("author", {}).get("name"),
            "content": commit.get("message", ""),
            "metadata": {
                "repo": repo,
                "ref": payload.get("ref"),
                "url": commit.get("url"),
            },
            "raw_payload": payload,
            "occurred_at": commit.get("timestamp", ""),
        })
    return events


def _parse_pull_request(payload: dict, repo: str) -> list[dict]:
    pr = payload.get("pull_request", {})
    action = payload.get("action", "")
    title = pr.get("title", "")
    body = pr.get("body", "") or ""
    content = f"[PR #{pr.get('number')}] {title}\n{body}".strip()

    return [{
        "source": "github",
        "source_id": f"pr_{pr.get('number')}_{action}",
        "event_type": "pull_request",
        "actor_email": None,
        "actor_name": payload.get("sender", {}).get("login"),
        "content": content,
        "metadata": {
            "repo": repo,
            "action": action,
            "pr_number": pr.get("number"),
            "url": pr.get("html_url"),
            "merged": pr.get("merged", False),
        },
        "raw_payload": payload,
        "occurred_at": pr.get("created_at", ""),
    }]


def _parse_pr_review(payload: dict, repo: str) -> list[dict]:
    review = payload.get("review", {})
    pr = payload.get("pull_request", {})
    content = f"Review on PR #{pr.get('number')}: {review.get('body', '')}"

    return [{
        "source": "github",
        "source_id": f"review_{review.get('id')}",
        "event_type": "pull_request_review",
        "actor_email": None,
        "actor_name": review.get("user", {}).get("login"),
        "content": content,
        "metadata": {
            "repo": repo,
            "pr_number": pr.get("number"),
            "state": review.get("state"),
        },
        "raw_payload": payload,
        "occurred_at": review.get("submitted_at", ""),
    }]


def _parse_issue_comment(payload: dict, repo: str) -> list[dict]:
    comment = payload.get("comment", {})
    issue = payload.get("issue", {})
    content = f"Comment on #{issue.get('number')}: {comment.get('body', '')}"

    return [{
        "source": "github",
        "source_id": f"comment_{comment.get('id')}",
        "event_type": "issue_comment",
        "actor_email": None,
        "actor_name": comment.get("user", {}).get("login"),
        "content": content,
        "metadata": {
            "repo": repo,
            "issue_number": issue.get("number"),
        },
        "raw_payload": payload,
        "occurred_at": comment.get("created_at", ""),
    }]
