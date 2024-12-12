"""
IPAM Syncronisation
"""
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn, MofNCompleteColumn

from application import logger
from application.modules.netbox.netbox import SyncNetbox
from application.models.host import Host


class SyncIPAM(SyncNetbox):
    """
    IP Syncer
    """
    console = None

    def sync_ips(self):
        """
        Sync IP Addresses
        """
        # Get current IPs
        current_ips = self.nb.ipam.ip_addresses

        object_filter = self.config['settings'].get(self.name, {}).get('filter')
        db_objects = Host.objects_by_filter(object_filter)
        total = db_objects.count()
        with Progress(SpinnerColumn(),
                      MofNCompleteColumn(),
                      *Progress.get_default_columns(),
                      TimeElapsedColumn()) as progress:
            self.console = progress.console.print
            task1 = progress.add_task("Updating IPs", total=total)
            for db_object in db_objects:
                hostname = db_object.hostname

                all_attributes = self.get_host_attributes(db_object, 'netbox_hostattribute')
                if not all_attributes:
                    progress.advance(task1)
                    continue
                cfg_ips = self.get_host_data(db_object, all_attributes['all'])

                for cfg_ip in cfg_ips['ips']:
                    try:
                        if 'ignore_ip' in cfg_ip['fields']:
                            continue

                        logger.debug(f"Working with {cfg_ip}")
                        address = cfg_ip['fields']['address']['value']
                        if not address:
                            continue
                        ip_query = {
                            'address': address,
                            'assigned_object': cfg_ip['fields']['assigned_object_id']['value'],
                        }
                        logger.debug(f"IPAM IPS Filter Query: {ip_query}")
                        if ip := current_ips.get(**ip_query):
                            # Update
                            if payload := self.get_update_keys(ip, cfg_ip):
                                self.console(f"* Update IP: for {address} on {hostname}")
                                ip.update(payload)
                            else:
                                self.console(f"* Already up to date IP: {address} on {hostname}")
                        else:
                            ### Create
                            self.console(f" * Create IP {address} on {hostname}")
                            payload = self.get_update_keys(False, cfg_ip)
                            logger.debug(f"Create Payload: {payload}")
                            ip = self.nb.ipam.ip_addresses.create(payload)
                    except Exception as exp:
                        self.console(f"Error with device: {exp}")
                progress.advance(task1)
