# CTFd Naumachia Plugin
Plugin for [CTFd](https://github.com/ctfd/ctfd) to integrate with [Naumachia](https://github.com/nategraf/Naumachia)

This plugin crestes the utilities needed to manage Naumachia user configs and certs from the CTFd interface.

### Admin interface:
* Field to specifiy the Naumachia challenge to link to
* (Planned) See all the clients with certs to access the challenge
* (Planned) Revoke a user's certificate to deny them access
* (Planned) Remove a user's certificate to force regeneration on next fetch

### User interface:
* Button to download (and generate) their OpenVPN client config file to connect to the challenge

## Installation
1. Clone this repo into the plugins directory of your CTFd instance
2. Edit config.py to include information for your registarar server
