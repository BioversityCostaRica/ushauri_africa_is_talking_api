import arrow
import logging
import os
import uuid
from datetime import datetime, timedelta
from urllib.request import urlretrieve
from pyramid.response import Response, FileResponse

from ushauri.processes import (
    getItemData,
    getItemResponses,
    getAudioFile,
    storeQuestion,
    isNumberAnAgent,
    isNumberAMember,
    getAgentStartItem,
    getMemberStartItem,
    getMemberAndGroup,
    getAudioFileName,
    recordLog,
)
from ushauri.processes.db.maintenance import getUserDetails, addAudio, setQuestionStatus

log = logging.getLogger(__name__)


def xml_response(resp):
    headers = [("Content-Type", "text/xml; charset=utf-8")]
    resp = Response(body=str(resp), headerlist=headers)
    return resp


def ivr_send_view(request):
    is_active = request.POST.get("isActive", "0")
    if is_active == 0:
        # We can store the EndCall information
        return xml_response("")
    audio_id = request.matchdict["audioid"]
    xml_data = "<Response>"
    xml_data = xml_data + "<Play url='{}'/>".format(
        request.url_for_static("static/audio/" + getAudioFileName(request, audio_id))
    )
    xml_data = xml_data + "</Response>"
    return xml_response(xml_data)


def ivr_reply_status_view(request):
    if request.method == "POST":
        question_id = request.matchdict["questionid"]
        audio_id = request.matchdict["audioid"]
        print("************************A99")
        call_status = request.POST.get("CallStatus", "failed")
        if call_status == "completed":
            setQuestionStatus(request, question_id, 3, audio_id)
        else:
            setQuestionStatus(request, question_id, -1, audio_id)
        print("************************A99")
    resp = Response()
    return resp


def ivr_voice_start_view(request):
    is_active = request.POST.get("isActive", "0")
    if is_active == 0:
        # We can store the EndCall information
        return xml_response("")
    number = request.POST.get("callerNumber", "failed")
    agent = isNumberAnAgent(request, number)
    # agent = None #Only for Skype test. Remove soon

    if agent is not None:
        menu_item = getAgentStartItem(request, agent)
        if menu_item is not None:
            xml_data = "<Response>"
            xml_data = xml_data + "<Redirect>{}</Redirect>".format(
                request.route_url("ivrget", itemid=menu_item)
            )
            xml_data = xml_data + "</Response>"
            return xml_response(xml_data)
        else:
            xml_data = "<Response>"
            xml_data = (
                xml_data + "<Say voice='en-US-Standard-C' playBeep='false' >"
                "Sorry your account does not have a active menu</Say>"
            )
            xml_data = xml_data + "</Response>"
            return xml_response(xml_data)
    else:
        member = isNumberAMember(request, number)
        if member is not None:
            menu_item = getMemberStartItem(request, member)
            if menu_item is not None:
                xml_data = "<Response>"
                xml_data = xml_data + "<Redirect>{}</Redirect>".format(
                    request.route_url("ivrget", itemid=menu_item)
                )
                xml_data = xml_data + "</Response>"
                return xml_response(xml_data)
            else:
                xml_data = "<Response>"
                xml_data = (
                    xml_data + "<Say voice='en-US-Standard-C' playBeep='false' >"
                    "Sorry your account does not have a active menu</Say>"
                )
                xml_data = xml_data + "</Response>"
                return xml_response(xml_data)
        else:
            xml_data = "<Response>"
            xml_data = (
                xml_data + "<Say voice='en-US-Standard-C' playBeep='false' >"
                "Contact your extension agent so he/she register you for this service</Say>"
            )
            xml_data = xml_data + "</Response>"
            return xml_response(xml_data)


def ivr_get_view(request):
    item_id = request.matchdict["itemid"]
    item_data = getItemData(request, item_id)

    is_active = request.POST.get("isActive", "0")
    if is_active == 0:
        # We can store the EndCall information
        return xml_response("")
    number = request.POST.get("callerNumber", "failed")

    recordLog(request, number, item_id)
    if item_data is not None:
        if item_data["item_type"] == 1:
            audio_data = getAudioFile(request, item_id)
            xml_data = "<Response>"
            xml_data = xml_data + "<GetDigits timeout='30' callbackUrl='{}'>".format(
                request.route_url("ivrpost", itemid=item_id)
            )
            if audio_data is None:
                xml_data = (
                    xml_data
                    + "<Say voice='en-US-Standard-C' playBeep='false' >{}</Say>".format(
                        item_data["item_desc"]
                    )
                )
            else:
                xml_data = xml_data + "<Play url='{}'/>".format(
                    request.url_for_static("static/audio/" + audio_data["audio_file"])
                )
            xml_data = xml_data + "</GetDigits>"
            xml_data = xml_data + "<Say>We did not get your answer. Good bye</Say>"
            xml_data = xml_data + "</Response>"
            return xml_response(xml_data)

        if item_data["item_type"] == 2:
            xml_data = "<Response>"
            audio_data = getAudioFile(request, item_id)
            xml_data = (
                xml_data + "<Record finishOnKey='#' "
                "maxLength='30' "
                "trimSilence='true' "
                "playBeep='true' callbackUrl = '{}'>".format(
                    request.route_url("ivrstore", itemid=item_id)
                )
            )
            if audio_data is None:
                xml_data = xml_data + "<Say>Record your message after the beep.</Say>"
            else:
                xml_data = xml_data + "<Play url='{}'/>".format(
                    request.url_for_static("static/audio/" + audio_data["audio_file"])
                )
            xml_data = xml_data + "</Record>"
            xml_data = xml_data + "</Response>"
            return xml_response(xml_data)
        if item_data["item_type"] == 3:
            xml_data = "<Response>"
            audio_data = getAudioFile(request, item_id)
            xml_data = xml_data + "<Play url='{}'/>".format(
                request.url_for_static("static/audio/" + audio_data["audio_file"])
            )

            if item_data["next_item"] is not None:
                xml_data = xml_data + "<Redirect>{}</Redirect>".format(
                    request.route_url("ivrget", itemid=item_data["next_item"])
                )
            xml_data = xml_data + "</Response>"
            return xml_response(xml_data)
    else:
        return xml_response("")


def ivr_post_view(request):
    item_id = request.matchdict["itemid"]
    item_data = getItemData(request, item_id)
    is_active = request.POST.get("isActive", "0")
    if is_active == 0:
        # We can store the EndCall information
        return xml_response("")
    if item_data is not None:
        item_responses = getItemResponses(request, item_id)

        soption = request.POST.get("dtmfDigits", "0")
        if isinstance(soption, str):
            try:
                noption = int(soption)
            except Exception as e:
                log.error("ivr_post_view error: {}".format(str(e)))
                xml_data = "<Response>"
                xml_data = (
                    xml_data + "<Say voice='en-US-Standard-C' playBeep='false' >Sorry, "
                    "you did not typed a number. "
                    "Redirecting you to the main menu</Say>"
                )
                xml_data = xml_data + "<Redirect>{}</Redirect>".format(
                    request.route_url("ivrstart")
                )
                xml_data = xml_data + "</Response>"
                return xml_response(xml_data)
        else:
            noption = soption
        for resp in item_responses:
            if resp["resp_num"] == noption:
                xml_data = "<Response>"
                xml_data = xml_data + "<Redirect>{}</Redirect>".format(
                    request.route_url("ivrget", itemid=resp["target_item"])
                )
                xml_data = xml_data + "</Response>"
                return xml_response(xml_data)
        xml_data = "<Response>"
        xml_data = xml_data + "<Say>Error, was not able to find a response</Say>"
        return xml_response(xml_data)
    else:
        xml_data = "<Response>"
        xml_data = (
            xml_data + "<Say voice='en-US-Standard-C' playBeep='false' >"
            "Invalid item</Say>"
        )
        xml_data = xml_data + "</Response>"
        return xml_response(xml_data)


def ivr_store_view(request):
    is_active = request.POST.get("isActive", 0)
    if is_active == 0:
        # We can store the EndCall information
        return xml_response("")
    recording_url = request.POST.get("recordingUrl", None)
    if recording_url is not None:
        uid = str(uuid.uuid4())
        number = request.POST.get("callerNumber", "")
        agent = isNumberAnAgent(request, number)
        if agent is not None:
            data = getUserDetails(request, agent)
            path = os.path.join(request.registry.settings["audioPath"], *[uid + ".wav"])
            urlretrieve(recording_url, path)
            ar = arrow.get(datetime.now() + timedelta(hours=3))  # Nairobi time
            addAudio(
                request,
                uid,
                "Audio recorded by agent "
                + data["user_name"]
                + " the "
                + ar.format("Do of MMMM, YYYY - HH:mm:ss"),
                uid + ".wav",
                2,
                data["user_id"],
            )
        else:
            group, member = getMemberAndGroup(request, number)
            path = os.path.join(
                request.registry.settings["repository"], *[uid + ".wav"]
            )
            urlretrieve(recording_url, path)
            storeQuestion(request, group, member, uid)
        return xml_response("")
    else:
        return xml_response("")


def ivr_get_audio_view(request):
    item_id = request.matchdict["audioid"]
    response = FileResponse(
        os.path.join(request.registry.settings["repository"], *[item_id + ".wav"]),
        request=request,
        content_type="audio/wav",
    )
    return response
