import xmltodict
import json
 
def parse_spml_to_json(xml_bytes):
    """
    Parses a complex SPML XML payload and extracts key subscriber data.
    """
    data = xmltodict.parse(xml_bytes)
    
    subscriber_data = data['soapenv:Envelope']['soapenv:Body']['spml:batchRequest']['request']['object']
    
    uid = subscriber_data.get('identifier')
    imsi = subscriber_data.get('hlr', {}).get('imsi')
    msisdn = subscriber_data.get('hlr', {}).get('ts11', {}).get('msisdn')
    
    return {
        "uid": uid,
        "imsi": imsi,
        "msisdn": msisdn,
        "raw_hlr_data": json.dumps(subscriber_data.get('hlr', {})),
        "raw_hss_data": json.dumps(subscriber_data.get('hss', {}))
    }
