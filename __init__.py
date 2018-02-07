from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.keys import get_key_class
from CTFd.plugins.challenges import BaseChallenge, CHALLENGE_CLASSES
from CTFd.models import db, Solves, WrongKeys, Keys, Challenges, Files, Tags
from CTFd import utils
from os import path
from io import BytesIO
from flask import session, abort, send_file
from .config import registrar_host, registrar_port
import json
import logging
import os

try:
    from urllib.parse import urlparse
    from urllib.request import urlopen
    from urllib.error import HTTPError
except ImportError:
    from urlparse import urlparse
    from urllib2 import urlopen
    from urllib2 import HTTPError


plugin_dirname = path.basename(path.dirname(__file__))
logger = logging.getLogger('naumachia')

class NaumachiaChallengeModel(Challenges):
    __mapper_args__ = {'polymorphic_identity': 'naumachia'}
    id = db.Column(None, db.ForeignKey('challenges.id'), primary_key=True)
    naumachia_name = db.Column(db.String(80))

    def __init__(self, name, description, value, category, naumachia_name, type='naumachia'):
        self.name = name
        self.description = description
        self.value = value
        self.category = category
        self.type = type
        self.naumachia_name = naumachia_name

class NaumachiaChallenge(BaseChallenge):
    id = "naumachia"  # Unique identifier used to register challenges
    name = "naumachia"  # Name of a challenge type
    templates = {  # Nunjucks templates used for each aspect of challenge editing & viewing
        'create': '/plugins/{0}/assets/naumachia-challenge-create.njk'.format(plugin_dirname),
        'update': '/plugins/{0}/assets/naumachia-challenge-update.njk'.format(plugin_dirname),
        'modal': '/plugins/{0}/assets/naumachia-challenge-modal.njk'.format(plugin_dirname),
    }
    scripts = {  # Scripts that are loaded when a template is loaded
        'create': '/plugins/{0}/assets/naumachia-challenge-create.js'.format(plugin_dirname),
        'update': '/plugins/{0}/assets/naumachia-challenge-update.js'.format(plugin_dirname),
        'modal': '/plugins/{0}/assets/naumachia-challenge-modal.js'.format(plugin_dirname),
    }

    @staticmethod
    def create(request):
        """
        This method is used to process the challenge creation request.

        :param request:
        :return:
        """

        # Create challenge
        chal = NaumachiaChallengeModel(
            name=request.form['name'],
            description=request.form['description'],
            value=request.form['value'],
            category=request.form['category'],
            type=request.form['chaltype'],
            naumachia_name=request.form['naumachia_name']
        )

        if 'hidden' in request.form:
            chal.hidden = True
        else:
            chal.hidden = False

        max_attempts = request.form.get('max_attempts')
        if max_attempts and max_attempts.isdigit():
            chal.max_attempts = int(max_attempts)

        db.session.add(chal)
        db.session.commit()

        flag = Keys(chal.id, request.form['key'], request.form['key_type[0]'])
        if request.form.get('keydata'):
            flag.data = request.form.get('keydata')
        db.session.add(flag)

        db.session.commit()

        files = request.files.getlist('files[]')
        for f in files:
            utils.upload_file(file=f, chalid=chal.id)

        db.session.commit()

    @staticmethod
    def read(challenge):
        """
        This method is in used to access the data of a challenge in a format processable by the front end.

        :param challenge:
        :return: Challenge object, data dictionary to be returned to the user
        """
        data = {
            'id': challenge.id,
            'name': challenge.name,
            'value': challenge.value,
            'description': challenge.description,
            'category': challenge.category,
            'naumachia_name': challenge.naumachia_name,
            'hidden': challenge.hidden,
            'max_attempts': challenge.max_attempts,
            'type': challenge.type,
            'type_data': {
                'id': NaumachiaChallenge.id,
                'name': NaumachiaChallenge.name,
                'templates': NaumachiaChallenge.templates,
                'scripts': NaumachiaChallenge.scripts,
            }
        }
        return challenge, data

    @staticmethod
    def update(challenge, request):
        """
        This method is used to update the information associated with a challenge. This should be kept strictly to the
        Challenges table and any child tables.

        :param challenge:
        :param request:
        :return:
        """
        challenge.name = request.form['name']
        challenge.description = request.form['description']
        challenge.value = int(request.form.get('value', 0)) if request.form.get('value', 0) else 0
        challenge.max_attempts = int(request.form.get('max_attempts', 0)) if request.form.get('max_attempts', 0) else 0
        challenge.category = request.form['category']
        challenge.naumachia_name = request.form['naumachia_name']
        challenge.hidden = 'hidden' in request.form
        db.session.commit()
        db.session.close()

    @staticmethod
    def delete(challenge):
        """
        This method is used to delete the resources used by a challenge.

        :param challenge:
        :return:
        """
        WrongKeys.query.filter_by(chalid=challenge.id).delete()
        Solves.query.filter_by(chalid=challenge.id).delete()
        Keys.query.filter_by(chal=challenge.id).delete()
        files = Files.query.filter_by(chal=challenge.id).all()
        for f in files:
            utils.delete_file(f.id)
        Files.query.filter_by(chal=challenge.id).delete()
        Tags.query.filter_by(chal=challenge.id).delete()
        NaumachiaChallengeModel.query.filter_by(id=challenge.id).delete()
        Challenges.query.filter_by(id=challenge.id).delete()
        db.session.commit()

    @staticmethod
    def attempt(chal, request):
        """
        This method is used to check whether a given input is right or wrong. It does not make any changes and should
        return a boolean for correctness and a string to be shown to the user. It is also in charge of parsing the
        user's input from the request itself.

        :param chal: The Challenge object from the database
        :param request: The request the user submitted
        :return: (boolean, string)
        """
        provided_key = request.form['key'].strip()
        chal_keys = Keys.query.filter_by(chal=chal.id).all()
        for chal_key in chal_keys:
            if get_key_class(chal_key.type).compare(chal_key.flag, provided_key):
                return True, 'Correct'
        return False, 'Incorrect'

    @staticmethod
    def solve(team, chal, request):
        """
        This method is used to insert Solves into the database in order to mark a challenge as solved.

        :param team: The Team object from the database
        :param chal: The Challenge object from the database
        :param request: The request the user submitted
        :return:
        """
        provided_key = request.form['key'].strip()
        solve = Solves(teamid=team.id, chalid=chal.id, ip=utils.get_ip(req=request), flag=provided_key)
        db.session.add(solve)
        db.session.commit()
        db.session.close()

    @staticmethod
    def fail(team, chal, request):
        """
        This method is used to insert WrongKeys into the database in order to mark an answer incorrect.

        :param team: The Team object from the database
        :param chal: The Challenge object from the database
        :param request: The request the user submitted
        :return:
        """
        provided_key = request.form['key'].strip()
        wrong = WrongKeys(teamid=team.id, chalid=chal.id, ip=utils.get_ip(request), flag=provided_key)
        db.session.add(wrong)
        db.session.commit()
        db.session.close()

def user_can_get_config():
    if utils.is_admin():
        return True
    if not (utils.authed() and utils.is_verified()):
        return False
    if not utils.user_can_view_challenges():
        return False
    if not (utils.ctf_started() and (utils.ctf_ended() or utils.view_after_ctf())):
        return False
    return True

def send_config(host, escaped_chalname, escaped_username):
    url = "http://{0}/{1}/get?cn={2}".format(host, escaped_chalname, escaped_username)
    logger.debug("Requesting: {0}".format(url))
    resp = urlopen(url, timeout=10)
    config = json.loads(resp.read().decode('utf-8')).encode('utf-8')
    return send_file(
        BytesIO(config),
        attachment_filename="{0}.ovpn".format(escaped_chalname),
        as_attachment=True
    )

def load(app):
    app.db.create_all()
    CHALLENGE_CLASSES['naumachia'] = NaumachiaChallenge

    # Create logger
    logger.setLevel(logging.INFO)

    log_dir = app.config['LOG_FOLDER']
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
        if user_can_get_config():
            chal = NaumachiaChallengeModel.query.filter_by(id=chalid).first_or_404()
            if chal.hidden:
                logger.info("[404] User {0} requested config for hidden challenge {1}".format(session['username'], chal.name))
                abort(404)
            
            escaped_username = urlparse.quote(session['username'])
            escaped_chalname = urlparse.quote(chal.naumachia_name, safe='')
            host = "{0}:{1}".format(registrar_host, registrar_port)

            try:
                resp = send_config(host, escaped_chalname, escaped_username)
                logger.info("[200] User {0} requested config for challenge {1}".format(session['username'], chal.name))
                return resp
            except HTTPError as err:
                if err.code != 404:
                    logger.info("[500] Config retrival failed for challenge {1}".format(chal.name))
                    raise

                try:
                    # The certs had not been generated yet. Generate them now
                    url = "http://{0}/{1}/add?cn={2}".format(host, escaped_chalname, escaped_username)
                    logger.debug("Requesting: {0}".format(url))
                    urlopen(url, timeout=10)

                    resp = send_config(host, escaped_chalname, escaped_username)
                    logger.info("[200] User {0} requested new config for challenge {1}".format(session['username'], chal.name))
                    return resp
                except HTTPError:
                    logger.info("[500] Config creation failed for challenge {1}".format(chal.name))
                    raise
        else:
            logger.info("[403] User {0} requested config for challenge {1}: Not authorized".format(session['username'], chalid))
            abort(403)
    
    register_plugin_assets_directory(app, base_path='/plugins/{0}/assets/'.format(plugin_dirname))
