from CTFd import utils
from CTFd.models import db, Solves, Fails, Flags, Challenges, ChallengeFiles, Tags, Hints
from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import BaseChallenge, CHALLENGE_CLASSES
from CTFd.plugins.flags import get_flag_class
from CTFd.utils.config import is_teams_mode
from CTFd.utils.config.visibility import challenges_visible
from CTFd.utils.uploads import delete_file
from CTFd.utils.user import get_ip, is_admin, authed, get_current_user, get_current_team
from flask import session, abort, send_file
from io import BytesIO
from urllib.parse import quote
import json
import logging
import os
import requests

from .config import config

plugin_dirname = os.path.basename(os.path.dirname(__file__))
logger = logging.getLogger('naumachia')
registrar_timeout = 10

class NaumachiaChallengeModel(Challenges):
    __mapper_args__ = {'polymorphic_identity': 'naumachia'}
    id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True
    )
    naumachia_name = db.Column(db.String(80))

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self.naumachia_name = kwargs["naumachia_name"]

class NaumachiaChallenge(BaseChallenge):
    id = "naumachia"  # Unique identifier used to register challenges
    name = "naumachia"  # Name of a challenge type
    templates = {  # Nunjucks templates used for each aspect of challenge editing & viewing
        'create': f'/plugins/{plugin_dirname}/assets/create.html',
        'update': f'/plugins/{plugin_dirname}/assets/update.html',
        'view': f'/plugins/{plugin_dirname}/assets/view.html',
    }
    scripts = {  # Scripts that are loaded when a template is loaded
        'create': f'/plugins/{plugin_dirname}/assets/create.js',
        'update': f'/plugins/{plugin_dirname}/assets/update.js',
        'view': f'/plugins/{plugin_dirname}/assets/view.js',
    }

    # Allows the default implementations of create and delete in BaseChallenge to work here.
    challenge_model = NaumachiaChallengeModel

    @classmethod
    def read(cls, challenge):
        """
        This method is in used to access the data of a challenge in a format processable by the front end.

        :param challenge:
        :return: Challenge object, data dictionary to be returned to the user
        """
        data = super().read(challenge)
        data['naumachia_name'] = challenge.naumachia_name
        return data

    @classmethod
    def update(cls, challenge, request):
        """
        This method is used to update the information associated with a challenge. This should be kept strictly to the
        Challenges table and any child tables.

        :param challenge:
        :param request:
        :return:
        """
        data = request.form or request.get_json()

        for attr, value in data.items():
            setattr(challenge, attr, value)

        db.session.commit()
        return challenge

def user_can_get_config():
    if is_admin():
        return True
    if not authed():
        return False
    if not challenges_visible():
        return False
    return True

def send_request(app, challenge, action, clientname):
    """
    Send a request to the registrar server for a given action and clientname.

    :param app: Flask app instance, used to obtain config values.
    :param challenge: The Naumachia challenge the request is for.
    :param action: Action to request.
        * "get" to retrieve an existing config and cert from the server.
        * "add" to create a new cert for the given user.
    :param clientname: The clientname for the cert should be created. Challenges are segmented by the
        given name, so if this is a team competition, this is the name of the team.
    :return: a response from the ``requests`` action.
    """
    scheme = app.config['REGISTRAR_USE_TLS'] and 'https' or 'http'
    host = app.config['REGISTRAR_HOST']
    port = app.config['REGISTRAR_PORT']
    url = f"{scheme}://{host}:{port}/{quote(challenge, safe='')}/{action}?cn={quote(clientname)}"

    kwargs = {
        "timeout": registrar_timeout,
        "headers": {
            "Accept": "application/json",
        },
    }

    if app.config['REGISTRAR_USE_TLS']:
        # If provided, set the CA cert to use as the root of trust for this connection.
        if app.config['REGISTRAR_CA_CERT']:
            kwargs["verify"] = app.config['REGISTRAR_CA_CERT']

        # If provided, set the client cert and key that should be used to authenticate.
        if app.config['REGISTRAR_CLIENT_CERT']:
            kwargs["cert"] = (app.config['REGISTRAR_CLIENT_CERT'],
                              app.config['REGISTRAR_CLIENT_KEY'])

    logger.debug(f"Requesting {url} with kwargs {kwargs}")
    return requests.get(url, **kwargs)



def send_config(app, challenge, clientname):
    resp = send_request(app, challenge, "get", clientname)
    resp.raise_for_status()

    # Response is the JSON encoded string of the client config.
    config = resp.json().encode('utf-8')
    return send_file(
        BytesIO(config),
        attachment_filename=f"{challenge}.ovpn",
        as_attachment=True
    )

def load(app):
    config(app)

    app.db.create_all()
    CHALLENGE_CLASSES['naumachia'] = NaumachiaChallenge

    # Intitialize logging.
    logger.setLevel(app.config.get('LOG_LEVEL', "INFO"))

    log_dir = app.config.get('LOG_FOLDER', os.path.join(os.path.dirname(__file__), 'logs'))
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, 'naumachia.log')

    if not os.path.exists(log_file):
        open(log_file, 'a').close()

    handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=10000)
    logger.addHandler(handler)
    logger.propagate = 0

    @app.route('/naumachia/config/<int:chalid>', methods=['GET'])
    def registrar(chalid):
        if not user_can_get_config():
            logger.info(f"[403] Client {session.get('clientname', '<not authed>')} requested config for challenge {chal.id}: Not authorized")
            abort(403)

        if is_teams_mode():
            clientname = get_current_team().name
        else:
            clientname = get_current_user().name

        chal = NaumachiaChallengeModel.query.filter_by(id=chalid).first_or_404()
        if chal.state == 'hidden':
            logger.info(f"[404] Client {clientname} requested config for hidden challenge {chal.name}")
            abort(404)

        # Get the config and return it to the user.
        # This may fail with 404 code if the config doesn't exist yet.
        try:
            resp = send_config(app, chal.naumachia_name, clientname)
            logger.info(f"[200] Client {clientname} requested config for challenge {chal.name}")
            return resp
        except requests.HTTPError as err:
            if err.response.status_code != 404:
                logger.info("[500] Config retrival failed for challenge {chal.name} and client {clientname}: {err}")
                raise

        try:
            # The certs had not been generated yet. Generate them now
            add_resp = send_request(app, chal.naumachia_name, "add", clientname)
            add_resp.raise_for_status()

            send_resp = send_config(app, chal.naumachia_name, clientname)
            logger.info(f"[200] Client {clientname} requested new config for challenge {chal.name}")
            return send_resp
        except requests.HTTPError as err:
            logger.info(f"[500] Config creation failed for challenge {chal.name} and client {clientname}: {err}")
            raise

    register_plugin_assets_directory(app, base_path=f'/plugins/{plugin_dirname}/assets/')
