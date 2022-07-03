from os import access, environ, R_OK
from os.path import isfile
from enum import Enum

def check_file_is_readable(key, filepath):
    if not isfile(filepath):
        raise ValueError(f'Provided {key} value is not a file: {filepath}')

    if not access(filepath, R_OK):
        raise ValueError(f'Provided {key} value is unreadable: {filepath}')


def config(app):
    '''
    REGISTRAR_HOST specifies the hostname at which the Naumachia registrar server is reachable from this host.
    '''
    app.config['REGISTRAR_HOST'] = environ.get('REGISTRAR_HOST', "localhost")

    '''
    REGISTRAR_PORT specifies the port on which the Naumachia registrar is available.
    '''
    app.config['REGISTRAR_PORT'] = int(environ.get('REGISTRAR_PORT', 3960))

    '''
    REGISTRAR_USE_TLS whether to use HTTPS to make requests to the registrar
    '''
    app.config['REGISTRAR_USE_TLS'] = environ.get('REGISTRAR_USE_TLS', 'False').strip().lower() == 'true'

    '''
    REGISTRAR_CA_CERT path to the CA certificate file for use in verifying the registrar TLS
    certificate. Provided as the registrar service is designed for use with local PKI.
    '''
    app.config['REGISTRAR_CA_CERT'] = environ.get('REGISTRAR_CA_CERT', None)
    if app.config['REGISTRAR_CA_CERT'] is not None:
        check_file_is_readable('REGISTRAR_CA_CERT', app.config['REGISTRAR_CA_CERT'])

    '''
    REGISTRAR_CLIENT_CERT path to a client certificate file for use when registrar client cert
    verification is enabled in conjunction with TLS.
    '''
    app.config['REGISTRAR_CLIENT_CERT'] = environ.get('REGISTRAR_CLIENT_CERT', None)
    if app.config['REGISTRAR_CLIENT_CERT'] is not None:
        check_file_is_readable('REGISTRAR_CLIENT_CERT', app.config['REGISTRAR_CLIENT_CERT'])

    '''
    REGISTRAR_CLIENT_KEY path to the private key corresponding to the certificate file listed above
    '''
    app.config['REGISTRAR_CLIENT_KEY'] = environ.get('REGISTRAR_CLIENT_KEY', None)
    if app.config['REGISTRAR_CLIENT_KEY'] is not None:
        check_file_is_readable('REGISTRAR_CLIENT_KEY', app.config['REGISTRAR_CLIENT_KEY'])

    # Ensure the TLS client options are consistent.
    if bool(app.config['REGISTRAR_CLIENT_CERT']) != bool(app.config['REGISTRAR_CLIENT_KEY']):
        raise ValueError('REGISTRAR_CLIENT_CERT and REGISTRAR_CLIENT_KEY options must be provided together')


