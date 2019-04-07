# sched-cli
ScheduleMaster CLI (mainly for West Valley Flying Club)

## quick usage example:

```bash
# either log in with username + password
./sched-cli.py login 12345-1 hunter12
# or copy any URL from the site (after logging in) and use adopturl
./sched-cli.py adopturl "https://my.schedulemaster.com/Schedule3.aspx?USERID=123456&SESSION=77778888&INITIAL=YES"

# check that it worked with `status` (WIP)
./sched-cli.py status

# get your own schedule (summary of upcoming bookings)
./sched-cli.py mysched

# or the full schedule (WIP, dumps JSON)
./sched-cli.py allsched
```
