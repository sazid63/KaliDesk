# Acceptable use

Kali Linux Windows Substitute is a tool for **authorised security testing,
learning and administration**. It is not an attack toolkit for other people's
systems.

## The rule

Only point it at systems you **own**, or that you have **explicit, written
permission** to test. "I found it online" is not permission. "It is for a good
cause" is not permission.

Unauthorised access to computer systems is a criminal offence in most
jurisdictions, including:

- the United States (Computer Fraud and Abuse Act, 18 U.S.C. § 1030);
- the United Kingdom (Computer Misuse Act 1990);
- the European Union (Directive 2013/40/EU and national implementations);
- and the equivalent law where you live.

You are responsible for knowing the law that applies to you.

## What the app does to help you stay lawful

- **The scope guard.** Targets outside the private ranges (`10/8`, `172.16/12`,
  `192.168/16`, `127/8`, `169.254/16`) are refused unless you deliberately tick a
  confirmation box that says you are authorised.
- **Confirmation is logged.** Every run is written to a local audit log, with the
  target and the result.
- **The AI cannot act.** It can suggest a command; you still have to confirm it.
- **Impact labels.** Catalog entries are labelled low / moderate / high impact so
  you know what you are about to do.

None of that is a licence. It is a guardrail.

## Sensible practice

- Agree scope in writing before you start, including IP ranges and time windows.
- Prefer a lab (your own VMs, a deliberately-vulnerable target such as
  [OWASP Juice Shop](https://owasp.org/www-project-juice-shop/),
  [DVWA](https://github.com/digininja/DVWA), or
  [TryHackMe](https://tryhackme.com)/[Hack The Box](https://www.hackthebox.com)).
- Keep the impact low on shared networks: low `--rate` on masscan, no aggressive
  or denial-of-service scan profiles.
- Stop and ask if a scan starts to affect a service that is not yours.

## Reporting

If you find a real vulnerability while testing something you own, use coordinated
disclosure. A maintainer's security contact can normally be found in
`security.txt` or their `SECURITY.md`. Do not publish exploit details before the
vendor has had a fair chance to fix it.

## The maintainers' position

The maintainers of this project do not condone, support or assist with
unauthorised testing. Issues and pull requests that are about attacking systems
without authorisation will be closed.
