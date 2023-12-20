"""
Sync Objects with Idoit
"""
#pylint: disable=no-member, too-many-locals, import-error
import requests
from requests.auth import HTTPBasicAuth

from application.models.host import Host
from application import app, log, logger
from application.modules.debug import ColorCodes as CC
from application.modules.plugin import Plugin

if app.config.get("DISABLE_SSL_ERRORS"):
    from urllib3.exceptions import InsecureRequestWarning
    from urllib3 import disable_warnings
    disable_warnings(InsecureRequestWarning)


class SyncIdoit(Plugin):
    """
    Idoit Sync Options 
    """
#   .-- Init
    def __init__(self):
        """
        Inital
        """
        self.log = log
        self.verify = not app.config.get('DISABLE_SSL_ERRORS')
#.
#   .-- Get Host Data
    def get_host_data(self, db_host, attributes):
        """
        Return commands for fullfilling of the netbox params
        """
        return self.actions.get_outcomes(db_host, attributes)
#.
#   . -- Request
    def request(self, data, method='POST'):
        """
        Handle Request to Idoit
        """
        address = self.config['address']
        url = f"{address}/src/jsonrpc.php"

        auth = HTTPBasicAuth(self.config['username'], self.config['password'])
        try:
            method = method.lower()
            logger.debug(f"Request ({method.upper()}) to {url}")
            logger.debug(f"Request Json Body: {data}")
            #pylint: disable=missing-timeout
            if method == 'post':
                response = requests.post(url, auth=auth, json=data)

            logger.debug(f"Response Text: {response.text}")
            if response.status_code == 403:
                raise Exception("Invalid Login, you may need to create a login token")
            try:
                response_json = response.json()
            except:
                raise
        except (ConnectionResetError, requests.exceptions.ProxyError):
            return {}
        return response_json
#.
#   .-- Get Devices
    def get_server(self, syncer_only=False):
        """
        Read full list of devices
        """
        print(f"{CC.OKGREEN} -- {CC.ENDC}Idoit: "\
              f"Read all servers")

        #TODO: Implement Filter for Objects manged by syncer
        json_data ={
            "version": "2.0",
            "method": "cmdb.objects.read",
            "params": {
                "filter": {
                    "type": "C__OBJTYPE__SERVER",
                    "status": "C__RECORD_STATUS__NORMAL"
                },
                "apikey": self.config["api_token"],
                "language": "de"
            },
            "id": 1
        }
        servers = self.request(json_data)['result']
        return {x['title']:x for x in servers}
#.
#   .--- Export Hosts
    def export_hosts(self):
        """
        Update Devices Table in Netbox
        """
        #pylint: disable=too-many-locals
        current_idoit_server = self.get_server(syncer_only=True)

        print(f"\n{CC.OKGREEN} -- {CC.ENDC}Start Sync")
        db_objects = Host.get_export_hosts()
        total = len(db_objects)
        counter = 0
        found_hosts = []

        for db_host in db_objects:
            hostname = db_host.hostname
            counter += 1
            process = 100.0 * counter / total

            all_attributes = self.get_host_attributes(db_host, 'idoit')
            if not all_attributes:
                continue

            found_hosts.append(db_host.hostname)

            custom_rules = self.get_host_data(db_host, all_attributes['all'])
            if custom_rules.get('ignore_host'):
                continue

            print(f"\n{CC.HEADER}({process:.0f}%) {hostname}{CC.ENDC}")

            if custom_rules.get('id_device_type_sync'):
                attribute_to_sync = custom_rules['id_device_type_sync']
                target_name = all_attributes['all'].get(attribute_to_sync)
                print(f"Device type with {target_name}")

            print(custom_rules)

        print(f"\n{CC.OKGREEN} -- {CC.ENDC}Cleanup")
        for hostname, host_data in current_idoit_server.items():
            if hostname not in found_hosts:
                print(f"{CC.OKBLUE} *{CC.ENDC} Delete {hostname}")
                print(host_data)
#.
#   .--- Import Hosts
    def import_hosts(self):
        """
        Import Objects from Netbox to the Syncer
        """

        for device, data in self.get_server()().items():
            host_obj = Host.get_host(device)
            print(f"\n{CC.HEADER}Process Device: {device}{CC.ENDC}")
            labels = data
            host_obj.update_host(labels)
            do_save = host_obj.set_account(account_dict=self.config)
            if do_save:
                host_obj.save()
#.
