#!/usr/bin/env python3
"""Import ODBC Data"""
#pylint: disable=logging-fstring-interpolation
import click

from syncerapi.v1 import (
    register_cronjob,
    cc,
    Host,
)

from syncerapi.v1.core import (
    logger,
    cli,
    app_config,
    Plugin,
)
from syncerapi.v1.inventory import run_inventory

try:
    import pypyodbc as pyodbc
except ImportError:
    logger.debug("Info: ODBC Plugin was not able to load required modules")

try:
    import sqlserverport
except ImportError:
    logger.debug("Info: Serverport module not available")

class ODBC(Plugin):
    """
    ODBC Plugin
    """

    def _innter_sql(self):
        """
        Mssql Functions
        """
        try:
            print(f"{cc.OKBLUE}Started {cc.ENDC} with account "\
                  f"{cc.UNDERLINE}{self.self.config['name']}{cc.ENDC}")


            logger.debug(self.config)
            serverport = self.config.get('serverport')
            if not serverport:
                serverport = sqlserverport.lookup(self.config['address'], self.config['instance'])
            server = f'{self.config["address"]},{serverport}'
            connect_str = f'DRIVER={{{self.config["driver"]}}};SERVER={server};'\
                          f'DATABASE={self.config["database"]};UID={self.config["username"]};'\
                          f'PWD={self.config["password"]};TrustServerCertificate=YES'
            logger.debug(connect_str)
            cnxn = pyodbc.connect(connect_str)
            cursor = cnxn.cursor()
            query = f"select {self.config['fields']} from {self.config['table']};"
            if "custom_query" in self.config and self.config['custom_query']:
                query = self.config['custom_query']
            logger.debug(query)
            cursor.execute(query)
            logger.debug("Cursor Executed")
            rows = cursor.fetchall()
            for row in rows:
                logger.debug(f"Found row: {row}")
                labels=dict(zip(self.config['fields'].split(","),row))
                hostname = labels[self.config['hostname_field']].strip()
                if 'rewrite_hostname' in self.config and self.config['rewrite_hostname']:
                    hostname = Host.rewrite_hostname(hostname,
                                                     self.config['rewrite_hostname'], labels)
                if app_config['LOWERCASE_HOSTNAMES']:
                    hostname = hostname.lower()
                yield hostname, labels
        except NameError as error:
            print(f"EXCEPTION: Missing requirements, pypyodbc or sqlserverport ({error})")

    def sql_import(self):
        """
        ODBC Import
        """
        for hostname, labels in self._innter_sql():
            print(f" {cc.OKGREEN}* {cc.ENDC} Check {hostname}")
            del labels[self.config['hostname_field']]
            host_obj = Host.get_host(hostname)
            host_obj.update_host(labels)
            do_save=host_obj.set_account(account_dict=self.config)
            if do_save:
                host_obj.save()
            else:
                print(f" {cc.WARNING} * {cc.ENDC} Managed by diffrent master")

    def sql_inventorize(self):
        """
        ODBC Inventorize
        """
        run_inventory(self.config, self._innter_sql())

#   . CLI and Cron

@cli.group(name='odbc')
def cli_odbc():
    """ODBC commands"""

def odbc_import(account):
    """
    ODBC Inner Import
    """
    odbc = ODBC(account)
    odbc.sql_import()
    odbc.save_log(f"Import data from {account}", "odbc_import")

@cli_odbc.command('import_hosts')
@click.argument('account')
def cli_odbc_import(account):
    """Import ODBC Hosts"""
    odbc_import(account)


def odbc_inventorize(account):
    """
    ODBC Inner Inventorize
    """
    odbc = ODBC(account)
    odbc.sql_inventorize()
    odbc.save_log(f"Inventorized data from {account}", "odbc_inventorize")


@cli_odbc.command('inventorize_hosts')
@click.argument('account')
def cli_odbc_inventorize(account):
    """Inventorize ODBC Data"""
    odbc_inventorize(account)

register_cronjob("ODBC: Import Hosts", odbc_import)
register_cronjob("ODBC: Inventorize Data", odbc_inventorize)
#.
