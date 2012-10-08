import os, struct, time, json, select, logging
###

L = logging.getLogger("cnscom")
Lmy = logging.getLogger("my")

###

callid_ping = 0
callid_start = 1
callid_stop = 2
callid_restart = 3
callid_status = 4
callid_tail = 5
callid_tailf_stop = 6 # Terminate previously initialized tailf mode

#

call_magic = '>'
resp_magic = '<'

call_struct_fmt = '!cBH'
resp_struct_fmt = '!ccH'

resp_return = 'R'
resp_exception = 'E'
resp_yield_message = 'M' # Used to propagate message from server to console
resp_tailf_data = 'T' # Used to send data in tail -f mode

###

class program_state_enum(object):
	'''Enum'''
	DISABLED = -1
	STOPPED = 0
	STARTING = 10
	RUNNING = 20
	STOPPING = 30
	FATAL = 200
	CFGERROR=201

	labels = {
		DISABLED: 'DISABLED',
		STOPPED: 'STOPPED',
		STARTING: 'STARTING',
		RUNNING: 'RUNNING',
		STOPPING: 'STOPPING',
		FATAL: 'FATAL',
		CFGERROR: 'CFGERROR',
	}


###


def svrcall(cnssocket, callid, params=""):
	'''
	Client side of console communication IPC call (kind of RPC / Remote procedure call).

	@param cnssocket: Socket to server (created by socket_uri factory)
	@param callid: one of callid_* identification
	@param params: string representing parameters that will be passed to server call
	@return: String returned by server or raises exception if server call failed
	'''

	paramlen = len(params)
	if paramlen >= 0x7fff:
		raise RuntimeError("Transmitted parameters are too long.")

	cnssocket.send(struct.pack(call_struct_fmt, call_magic, callid, paramlen)+params)

	while 1:
		retype, params = svrresp(cnssocket)

		if retype == resp_return:
			# Remote server call returned normally
			return params
		
		elif retype == resp_exception:
			# Remove server call returned exception
			raise RuntimeError(params)
		
		elif retype == resp_yield_message:
			# Remote server call returned yielded message -> we will continue receiving
			obj = json.loads(params)
			obj = logging.makeLogRecord(obj)
			if Lmy.getEffectiveLevel() <= obj.levelno: # Print only if log level allows that
				Lmy.handle(obj)
			continue

		else:
			raise RuntimeError("Unknown/invalid server response: {0}".format(retype))

###

def svrresp(cnssocket, loop_detector=True):
	'''Receive and parse one server response - used inherently by svrcall.

	@param cnssocket: Socket to server (created by socket_uri factory)
	@param loop_detector: If set to True, logs warning when server is not responding in 2 seconds	
	@return: tuple(retype, params) - retype is cnscom.resp_* integer and params are data attached to given response
	'''

	x = time.time()
	resp = ""
	while len(resp) < 4:
		rlist, _, _ = select.select([cnssocket],[],[], 5)
		if len(rlist) == 0:
			if loop_detector and time.time() - x > 2: L.error("Looping detected")
			continue
		ndata = cnssocket.recv(4 - len(resp))
		if len(ndata) == 0:
			raise EOFError("It looks like server closed connection")

		resp += ndata

	magic, retype, paramlen = struct.unpack(resp_struct_fmt, resp)
	assert magic == resp_magic

	# Read rest of the response (size given by paramlen)
	params = ""
	while paramlen > 0:
		ndata = cnssocket.recv(paramlen)
		params += ndata
		paramlen -= len(ndata)

	return retype, params

###

def parse_json_kwargs(params):
	'''Used when params are transfered as JSON - it also handles situation when 'params' is empty string '''
	if params == '': return dict()
	return json.loads(params)

###

class svrcall_error(RuntimeError):
	'''
	Exception used to report error to the console without leaving trace in server error log.
	'''
	pass
