# uw-section-avail

## Summary

- Monitors one or more University of Waterloo class sections.
- Supports multiple terms, courses, class numbers, and notification email addresses.
- Sends an email **only when a monitored section changes from full to open**.
- Uses **GitHub Actions** to run the monitor.
- Uses **cron-job.org** instead of GitHub schedules to trigger the workflow every 30 minutes.

## GitHub workflow

Your workflow should use only:

```yaml
on:
  workflow_dispatch:
```

Do **not** include a GitHub `schedule:` trigger when using cron-job.org.

## GitHub secrets

Create these repository secrets:

| Secret | Purpose |
|---|---|
| `GMAIL_ADDRESS` | Gmail account used to send notifications |
| `GMAIL_APP_PASSWORD` | Gmail App Password for the sending account |
| `NOTIFY_EMAIL` | One or more comma-separated recipient email addresses |

Example:

```text
me@gmail.com,friend@gmail.com,parent@uwaterloo.ca
```

## Configuring monitored courses

Edit `config.yml`.

Example:

```yaml
default_level: under
project_name: uw-section-avail

courses:
  - term: "1269"
    subject: AFM
    course_number: "482"
    class_numbers:
      - "3453"

  - term: "1269"
    subject: CLAS
    course_number: "104"
    class_numbers:
      - "3622"

  - term: "1259"
    subject: CLAS
    course_number: "202"
    class_numbers:
      - "8374"
```

Each course can contain one or many class numbers.

## Manual testing

Open **Actions → Check Waterloo sections → Run workflow**.

A notification is sent only if a monitored section has just changed from **full** to **open**.

To temporarily test email delivery, uncomment:

```python
# send_email(sections, project_name)
# print("Test email sent.")
```

Run the workflow once, verify the email arrives, then comment those lines again.

## Scheduling with cron-job.org

1. Create a **fine-grained GitHub Personal Access Token**.
2. Give it **Actions: Read and write** permission for this repository.
3. Create a cron-job.org HTTP job.

Endpoint:

```text
https://api.github.com/repos/YOUR_USERNAME/uw-section-avail/actions/workflows/check-sections.yml/dispatches
```

Method:

```text
POST
```

Headers:

```text
Authorization: Bearer YOUR_TOKEN
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
```

Body:

```json
{
  "ref": "main"
}
```

Timezone:

```text
America/Toronto
```

Create two cron jobs.

### Job 1

```text
5 8-20 * * *
```

Runs:

```text
8:05 AM, 9:05 AM, ..., 8:05 PM
```

### Job 2

```text
35 8-19 * * *
```

Runs:

```text
8:35 AM, 9:35 AM, ..., 7:35 PM
```

## Notification behaviour

- Full → Full: no email
- Full → Open: email
- Open → Open: no duplicate email
- Open → Full: state updated
- Full again → Open again: email again

## state.json

`state.json` stores the previous status of every monitored section to prevent duplicate notifications.

Reset it to:

```json
{}
```

only if you intentionally want to forget all previous section states.

## Security

- Never commit Gmail credentials.
- Never commit GitHub tokens.
- Restrict the GitHub token to this repository only.
