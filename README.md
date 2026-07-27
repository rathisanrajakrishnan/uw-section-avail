# uw-section-avail

Checks multiple University of Waterloo courses every 30 minutes from **8:15 AM through 7:45 PM America/Toronto time** and sends a Gmail notification when a monitored class changes from **full** to **open**.

The included example configuration monitors:

- Term `1269`, `AFM 482`, class `3453`
- Term `1269`, `CLAS 104`, class `3622`
- Term `1259`, `CLAS 202`, class `8374`

## 1. Create the GitHub repository

Create a GitHub repository named **`uw-section-avail`** and upload every file from this folder, including the hidden `.github` folder. Keep `state.json`; it prevents duplicate emails while a section remains open.

From Terminal, you can instead run:

```bash
git init
git add .
git commit -m "Initial section monitor"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/uw-section-avail.git
git push -u origin main
```

## 2. Add Gmail credentials

Use a Gmail account with Google 2-Step Verification enabled and create a 16-character Google App Password. Do not use your regular Gmail password.

In GitHub, open **Settings → Secrets and variables → Actions → New repository secret**, then add:

| Secret | Value |
|---|---|
| `GMAIL_ADDRESS` | Gmail address used to send the notification |
| `GMAIL_APP_PASSWORD` | 16-character Google App Password |
| `NOTIFY_EMAIL` | Address that receives notifications; it may be the same Gmail address |

## 3. Edit the monitored courses

Open `config.yml`. Add one block under `courses` for every course. Each course can contain one or several class numbers:

```yaml
default_level: under
project_name: uw-section-avail

courses:
  - term: "1269"
    subject: AFM
    course_number: "482"
    class_numbers:
      - "3453"
      - "3454"

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

Class numbers are the values in the first **Class** column, not labels such as `LEC 002`.

To remove a course, delete its complete block. Keep the indentation exactly as shown.

## 4. Test it

1. Open the repository's **Actions** tab.
2. Select **Check Waterloo sections**.
3. Click **Run workflow**.
4. Open the run to see the status of every configured section.

Manual runs proceed at any time. Scheduled runs occur at **8:15 AM, 8:45 AM, 9:15 AM, ... through 7:45 PM** in `America/Toronto`, automatically accounting for daylight-saving changes. GitHub may start scheduled workflows a few minutes late.

## Notification behaviour

- Full → open: sends one email.
- Still open: does not send duplicate emails.
- Open → full: updates the saved state.
- Full → open again: sends another email.
- Multiple sections open in the same check: combines them into one email.
- Website, parsing, or email error: the workflow fails visibly instead of silently reporting a wrong result.

## Important

- The monitor only reports availability; it cannot enrol or reserve a seat.
- A visible seat may still be unavailable to you because of reserves, eligibility rules, holds, or enrolment timing.
- When replacing an older single-course version, upload the new `monitor.py`, `config.yml`, and `README.md`. Resetting `state.json` to `{}` is recommended because the new version uses unique state keys for each term/course/class combination.
