# CTFd Naumachia Plugin

Plugin for [CTFd](https://github.com/ctfd/ctfd) to integrate with [Naumachia](https://github.com/nategraf/Naumachia)

This plugin creates the utilities needed to manage Naumachia user configs and certs from the CTFd
interface.

It adds a new "naumachia" challenge type to the admin interface. In creating the challenge, specify
the name of the challenge in Naumachia that this challenge links to.

In the user interface for the challenge there will be an attachment for an OpenVPN config file. When
the user clicks on this attachment, the plugin will talk to the registrar server to issue and
retrieve the OpenVPN config, including client certificates and keys, to return the user.


## Installation

1. Clone this repo into the plugins directory of your CTFd instance.
2. Edit config.py to include information for your Naumachia registrar server.

### Connecting to the Registrar Server

Connection to the registrar server should be restricted to the CTFd instance, and any other trusted
hosts. Depending on your environment, you can accomplish this deploying the CTFd instance and
registrar server (i.e. Naumachia) to a private network and ensure the registrar server is behind a
firewall such that only your CTFd instance can talk to it.

Another, somewhat more robust option, is to use mTLS. Naumachia includes functionality to generate
server and client TLS certs, via a local PKI, for use in authenticating and encrypting this connection.
Add the appropriate settings to your `config.yml` file in Naumachia to generate the certs via
`configure.py`. Once you've done this, copy the client cert and key to the `.data/CTFd/ssl/ctfd.crt`
and `.data/CTFd/ssl/ctfd.key`, or another location specified in your CTFd config. See `config.py`
for more information on the options.

