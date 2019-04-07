# sched-cli
ScheduleMaster CLI (mainly for West Valley Flying Club)

## quick usage example:

```bash
# either log in with username + password
./sched-cli.py login 12345-1 hunter12
# or copy any URL from the site (after logging in) and use adopturl
./sched-cli.py adopturl "https://my.schedulemaster.com/Schedule3.aspx?USERID=123456&SESSION=77778888&INITIAL=YES"

# check that it worked with `me`
./sched-cli.py me

# get your own schedule (summary of upcoming bookings)
./sched-cli.py mysched

# or the full schedule (WIP, dumps JSON)
./sched-cli.py allsched
# still useful - e.g. find all C-172s at KPAO
./sched-cli allsched | jq '.r[] | select(.model|contains("C-172SP")) | select(.location|contains("PALO ALTO"))' -c

# TODO:
- non-JSON view for all scheduled reservations, with resource and time filtering
- ability to book a reservation
- cmd to find an available reservation aircraft given time and model constraints
```
