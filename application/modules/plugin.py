"""
Alle Stuff shared by the plugins
"""
#pylint: disable=too-few-public-methods
#pylint: disable=logging-fstring-interpolation

from pprint import pformat
from collections import namedtuple
import requests
from application import logger
from application.modules.custom_attributes.models import CustomAttributeRule as \
    CustomAttributeRuleModel
from application.modules.custom_attributes.rules import CustomAttributeRule


class Plugin():
    """
    Base Class for all Plugins
    """
    rewrite = False
    filter = False
    custom_attributes = False
    debug = False
    account = False
    verify = True

    dry_run = False


    def inner_request(self, method, url, data, headers):
        """
        Requst Module for all HTTP Requests
        by Plugin
        """
        logger.debug(f"Request ({method.upper()}) to {url}")
        logger.debug(f"Request Body: {pformat(data)}")
        logger.debug(f"Request Headers: {headers}")

        method = method.lower()
        payload = {
            'headers': headers,
            'params': data,
            'verify': self.verify,
            'timeout': 20,
        }

        if headers.get('Content-Type') == "application/json":
            del payload['params']
            payload['json'] = data

        if path := self.save_requests:
            open(path, "a").write(f"{method}||{url}||{payload}\n")

        if self.dry_run:
            logger.info(f"Body: {pformat(data)}")
            Struct = namedtuple('response', ['status_code', 'headers'])
            if method != 'get':
                return Struct(status_code=200, headers={}), {}


        jobs = {
            'get': requests.get(url, **payload),
            'post': requests.post(url, **payload),
            'put': requests.put(url, **payload),
            'delete': requests.delete(url, **payload),
        }
        resp = jobs[method]
        resp_json = resp.json()
        return jobs[method], resp_json


    def init_custom_attributes(self):
        """
        Load Rules for custom Attributes
        """
        self.custom_attributes = CustomAttributeRule()
        self.custom_attributes.debug = self.debug
        self.custom_attributes.rules = \
                        CustomAttributeRuleModel.objects(enabled=True).order_by('sort_field')

    def get_host_attributes(self, db_host, cache):
        """
        Return Host Attributes or False if Host should be ignored
        """
        # Get Attributes
        cache += "_hostattribute"
        db_host.cache.setdefault(cache, {})
        if 'attributes' in db_host.cache[cache]:
            logger.debug(f"Using Attribute Cache for {db_host.hostname}")
            if 'ignore_host' in db_host.cache[cache]['attributes']['filtered']:
                return False
            return db_host.cache[cache]['attributes']
        attributes = {}
        attributes.update({x:y for x,y in db_host.labels.items() if y})
        attributes.update({x:y for x,y in db_host.inventory.items() if y})

        self.init_custom_attributes()
        attributes.update(self.custom_attributes.get_outcomes(db_host, attributes))

        attributes_filtered = {}
        if self.rewrite:
            for rewrite, value in self.rewrite.get_outcomes(db_host, attributes).items():
                realname = rewrite[4:]
                if rewrite.startswith('add_'):
                    attributes[realname] = value
                elif rewrite.startswith('del_'):
                    del attributes[realname]
        data = {
            'all': attributes,
            'filtered': attributes_filtered,
        }

        if self.filter:
            attributes_filtered = self.filter.get_outcomes(db_host, attributes)
            data['filtered'] = attributes_filtered
            if attributes_filtered.get('ignore_host'):
                db_host.cache[cache]['attributes'] = data
                db_host.save()
                return False

        db_host.cache[cache]['attributes'] = data
        db_host.save()
        return data
