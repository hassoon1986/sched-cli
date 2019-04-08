#!/usr/bin/python3
import argparse
import datetime
import json
import re
import logging
import os
import urllib.parse
import unicodedata
import collections
from types import SimpleNamespace

import dateutil.parser
import requests
import lxml.html

logger = logging.getLogger(__name__)

ROOT = 'https://my.schedulemaster.com/'

# Define Schedule named tuple (all fields optional)
fields = [
    'owner',
    'start_time',
    'end_time',
    'resource',
    'notes',
]
Schedule = collections.namedtuple('Schedule', fields, defaults=(None,) * len(fields))
del fields

class ScheduleMasterAPI:
    def __init__(self, args):
        self.session = requests.Session()
        self.session.headers = {
            'User-agent': 'ScheduleMasterAPI (python3, experimental)',
        }
        self.state_path = args.config_file
        try:
            self._load_state()
        except Exception:
            pass

    def _load_state(self):
        with open(self.state_path, 'r') as inp:
            js = json.load(inp)
            self.__dict__.update(js)

    def _save_state(self):
        with open(self.state_path, 'w') as out:
            js = {}
            for k, v in self.__dict__.items():
                try:
                    json.dumps({k:v})
                except Exception:
                    pass
                else:
                    js[k] = v
            json.dump(js, out)

    def _adopt(self, userid, session):
        self.userid = userid
        self.sessionid = session
        self._save_state()
    def cmd_adopt(self, args):
        self._adopt(args.userid, args.session)

    def _adopt_url(self, url):
        uo = urllib.parse.urlparse(url)
        uargs = dict(urllib.parse.parse_qsl(uo.query.lower()))
        self._adopt(uargs['userid'], uargs['session'])
    def cmd_adopturl(self, args):
        self._adopt_url(args.url)

    def cmd_login(self, args):
        resp = self.session.post(ROOT + 'login.asp', data={
            'USERID': args.username,
            'DATA': args.password,
            'CMD': 'LOGIN',
            'pagename': 'my.schedulemaster.com',
        })
        resp.raise_for_status()

        loc = resp.headers.get('Location')
        if 'USERID=' in loc:
            self._adopt_url(loc)
        else:
            raise ValueError("Login failed")

    def _add_auth(self, params=None):
        if not params:
            params = {}
        params.update({'userid': self.userid, 'session': self.sessionid})
        return params

    def _request(self, path, params=None, data=None, method='GET', parse=True):
        resp = self.session.request(method, ROOT + path, params=self._add_auth(params), data=data, timeout=31)
        resp.raise_for_status()
        if 'Schedule Master could not validate your user or session information.' in resp.text:
            raise ValueError("Login information expired")
        if parse:
            return lxml.html.fromstring(resp.text)
        else:
            return resp.text

    def get_my_schedule(self):
        root = self._request('SchedList.aspx', params={'mysched': 1})

        def clean(txt):
            return unicodedata.normalize('NFKD', txt).strip()

        out = []
        for td in root.cssselect('td.Item, td.AltItem'):
            elms = [clean(elm.text_content()) for elm in td.cssselect('div')]
            if len(elms) != 7: continue  # cannot parse
            _, start, end, resource, _, notes, _ = elms
            start = re.sub(' ?- ?$', '', start)
            out.append(Schedule(
                start_time=dateutil.parser.parse(start),
                end_time=dateutil.parser.parse(end),
                owner='you',
                notes=notes,
                resource=resource,
            ))

        return out
    def cmd_mysched(self, args):
        print('\n'.join(str(x) for x in self.get_my_schedule()))

    def get_all_schedules(self, start_time:datetime.datetime, end_time:datetime.datetime):
        root = self._request('Schedule3.aspx')
        rjs = json.loads(root.cssselect('#ctl00_CPL1_h_jsonRes')[0].value)

        resp = self.session.get(ROOT + 'SchedData.aspx', params={
            'ver': 'sch_0.0.1',
            'user_id': self.userid,
            'ses_id': self.sessionid,
            'c': 'fCal',
            'subCmd': 'sch',
            'userfilter': 0,
            'start':start_time.strftime('%Y-%m-%d'),
            'end':end_time.strftime('%Y-%m-%d'),
        }, timeout=31)
        resp.raise_for_status()
        return rjs, resp.json()

    def _compute_status(self, res):
        try:
            return res.get('slbl').replace('warn_', '').replace('.jpg', '')
        except Exception:
            return None

    def _filter_resources(self, resources, args):
        if args.resources:
            rs_filt = [r.strip() for r in args.resources.lower().split(',')]
            resources = [r for r in resources if r['title'].lower() in rs_filt or
                                                 r['NNO'].lower() in rs_filt or
                                                 r['id'].lower() in rs_filt]
        if args.models:
            m_filt = [r.strip() for r in args.models.lower().split(',')]
            resources = [r for r in resources if any(m in m_filt for m in r['model'].lower().split(','))]

        if args.location:
            l_filt = [r.strip() for r in args.location.lower().split(',')]
            resources = [r for r in resources if any(l in r['location'].lower() for l in l_filt)]

        if args.statuses:
            resources = [r for r in resources if str(self._compute_status(r)) in args.statuses]

        return resources

    def cmd_allsched(self, args):
        start = datetime.datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
        end = start + datetime.timedelta(1)
        if args.start_time:
            start = dateutil.parser.parse(args.start_time)
            end = start + datetime.timedelta(1)
        if args.end_time:
            end = dateutil.parser.parse(args.end_time)

        resources, reservations = self.get_all_schedules(start, end)
        resources = self._filter_resources(resources, args)
        resource_map = {int(r['id']): r for r in resources}

        for r in reservations:
            r['start_dt'] = dateutil.parser.parse(r['start'])
            r['end_dt'] = dateutil.parser.parse(r['end'])
        reservations = [r for r in reservations if r['start_dt'] >= start and
                                                   r['end_dt'] <= end and
                                                   r['resourceId'] in resource_map]

        reservations.sort(key=lambda k: (k['resourceId'], k['start']))

        # RENDER CODE
        print(start.isoformat(), '->', end.isoformat())

        seen_res = set()
        for sched in reservations:
            res = resource_map[sched['resourceId']]
            if res['id'] not in seen_res:
                seen_res.add(res['id'])
                print()
                print(self._render_resource(res))
            print(sched['start'], sched['end'], sched['name'], sched['dest'])

        for res in resources:
            if res['id'] not in seen_res:
                print()
                print(self._render_resource(res))
                print("no reservations")

    def _render_resource(self, res):
        status = self._compute_status(res) or 'unk'
        res = SimpleNamespace(**res)
        return '#{0.id} {status}  {0.title}  @ {0.location}  ({0.model})'.format(res, status=status)

    def cmd_listres(self, args):
        resources, _ = self.get_all_schedules(datetime.datetime.now(), datetime.datetime.now())
        resources = self._filter_resources(resources, args)

        for res in resources:
            print(self._render_resource(res))

    def cmd_me(self, args):
        root = self._request('UserInfo.aspx', params={'GETUSER':'M'})
        print(root.cssselect('div.headerleft.middle')[0].text_content().strip())


# curl 'login.asp' -H 'User-Agent: ScheduleMaster-python (experimental)' -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' -H 'Accept-Language: en-US,en;q=0.5' --compressed -H 'Referer: https://my.schedulemaster.com/' -H 'Content-Type: application/x-www-form-urlencoded' --data 'USERID=12117-1&DATA=paraslide+spools&CMD=LOGIN&reqPage=&calling=&timestamp=&return_to=&pagename=my.schedulemaster.com'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config-file', default=os.path.expanduser('~/.schedulemaster-api.json'), help='JSON state file path')

    sp = parser.add_subparsers(dest='command', required=True)

    p = sp.add_parser('login')
    p.add_argument('username', help='username (e.g. 12345-1)')
    p.add_argument('password', help='password')

    p = sp.add_parser('adopt')
    p.add_argument('userid', type=int)
    p.add_argument('session', type=int)

    p = sp.add_parser('adopturl')
    p.add_argument('url')

    p = sp.add_parser('mysched')

    p = sp.add_parser('allsched')
    p.add_argument('-s', '--start-time', help='starting time (default: today)')
    p.add_argument('-e', '--end-time', help='ending time (default: today)')
    p.add_argument('-r', '--resources', help='comma-separated list of resources to show')
    p.add_argument('-m', '--models', help='comma-separated list of models to show')
    p.add_argument('--statuses', default='yel,grn,gry,None', help='comma-separated list of acceptible resource statuses')
    p.add_argument('-l', '--location', help='substring of location (default any)')

    p = sp.add_parser('me')

    p = sp.add_parser('listres')
    p.add_argument('-r', '--resources', help='comma-separated list of resources to show')
    p.add_argument('-m', '--models', help='comma-separated list of models to show')
    p.add_argument('-l', '--location', help='substring of location (default any)')
    p.add_argument('--statuses', default='yel,grn,gry,None', help='comma-separated list of acceptible resource statuses')

    args = parser.parse_args()

    api = ScheduleMasterAPI(args)

    getattr(api, 'cmd_' + args.command)(args)

# Login:
# curl 'https://my.schedulemaster.com/login.asp' -H 'User-Agent: ScheduleMaster-python (experimental)' -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' -H 'Accept-Language: en-US,en;q=0.5' --compressed -H 'Referer: https://my.schedulemaster.com/' -H 'Content-Type: application/x-www-form-urlencoded' --data 'USERID=12117-1&DATA=paraslide+spools&CMD=LOGIN&reqPage=&calling=&timestamp=&return_to=&pagename=my.schedulemaster.com'

if __name__ == '__main__':
    main()
