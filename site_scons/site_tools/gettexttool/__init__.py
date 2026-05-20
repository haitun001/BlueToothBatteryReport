"""This tool allows generation of gettext .mo compiled files, pot files from source code files
and pot files for merging.

Three new builders are added into the constructed environment:

- gettextMoFile: generates .mo file from .pot file using msgfmt.
- gettextPotFile: Generates .pot file from source code files.
- gettextMergePotFile: Creates a .pot file appropriate for merging into existing .po files.

To properly configure get text, define the following variables:

- gettext_package_bugs_address
- gettext_package_name
- gettext_package_version


"""

import ast
import shutil
import struct
import subprocess

from SCons.Action import Action


def exists(env):
	return True


XGETTEXT_COMMON_ARGS = (
	"--msgid-bugs-address='$gettext_package_bugs_address' "
	"--package-name='$gettext_package_name' "
	"--package-version='$gettext_package_version' "
	"--keyword=pgettext:1c,2 "
	"-c -o $TARGET $SOURCES"
)


def _decode_po_string(text: str) -> str:
	return ast.literal_eval(text)


def _parse_po_messages(po_path: str) -> dict[str, str]:
	messages: dict[str, str] = {}
	fuzzy = False
	msgctxt: str | None = None
	msgid: str | None = None
	msgid_plural: str | None = None
	msgstrs: dict[int, str] = {}
	currentField: tuple[str, int | None] | None = None

	def _commit() -> None:
		nonlocal fuzzy, msgctxt, msgid, msgid_plural, msgstrs, currentField
		if msgid is None or fuzzy:
			fuzzy = False
			msgctxt = None
			msgid = None
			msgid_plural = None
			msgstrs = {}
			currentField = None
			return

		key = msgid
		if msgctxt is not None:
			key = f"{msgctxt}\x04{key}"
		if msgid_plural is not None:
			key = f"{key}\x00{msgid_plural}"
			maxIndex = max(msgstrs, default=-1)
			value = "\x00".join(msgstrs.get(index, "") for index in range(maxIndex + 1))
		else:
			value = msgstrs.get(0, "")
		messages[key] = value

		fuzzy = False
		msgctxt = None
		msgid = None
		msgid_plural = None
		msgstrs = {}
		currentField = None

	with open(po_path, "r", encoding="utf-8") as poFile:
		for rawLine in poFile:
			line = rawLine.rstrip("\r\n")
			if not line:
				_commit()
				continue
			if line.startswith("#,"):
				if "fuzzy" in line:
					fuzzy = True
				continue
			if line.startswith("#"):
				continue
			if line.startswith("msgctxt "):
				msgctxt = _decode_po_string(line[8:])
				currentField = ("msgctxt", None)
				continue
			if line.startswith("msgid_plural "):
				msgid_plural = _decode_po_string(line[13:])
				currentField = ("msgid_plural", None)
				continue
			if line.startswith("msgid "):
				msgid = _decode_po_string(line[6:])
				currentField = ("msgid", None)
				continue
			if line.startswith("msgstr["):
				indexEnd = line.index("]")
				index = int(line[7:indexEnd])
				msgstrs[index] = _decode_po_string(line[indexEnd + 2 :])
				currentField = ("msgstr", index)
				continue
			if line.startswith("msgstr "):
				msgstrs[0] = _decode_po_string(line[7:])
				currentField = ("msgstr", 0)
				continue
			if line.startswith('"') and currentField is not None:
				extra = _decode_po_string(line)
				fieldName, fieldIndex = currentField
				if fieldName == "msgctxt":
					msgctxt = (msgctxt or "") + extra
				elif fieldName == "msgid":
					msgid = (msgid or "") + extra
				elif fieldName == "msgid_plural":
					msgid_plural = (msgid_plural or "") + extra
				else:
					msgstrs[fieldIndex or 0] = msgstrs.get(fieldIndex or 0, "") + extra

	_commit()
	return messages


def _write_mo(messages: dict[str, str], mo_path: str) -> None:
	items = sorted(messages.items())
	ids = b""
	strs = b""
	offsets: list[tuple[int, int, int, int]] = []
	for msgid, msgstr in items:
		msgidBytes = msgid.encode("utf-8")
		msgstrBytes = msgstr.encode("utf-8")
		offsets.append((len(msgidBytes), len(ids), len(msgstrBytes), len(strs)))
		ids += msgidBytes + b"\0"
		strs += msgstrBytes + b"\0"

	numStrings = len(offsets)
	headerSize = 7 * 4
	idsTableOffset = headerSize
	strsTableOffset = idsTableOffset + numStrings * 8
	idsPoolOffset = strsTableOffset + numStrings * 8
	strsPoolOffset = idsPoolOffset + len(ids)

	with open(mo_path, "wb") as moFile:
		moFile.write(
			struct.pack(
				"<7I",
				0x950412DE,
				0,
				numStrings,
				idsTableOffset,
				strsTableOffset,
				0,
				0,
			),
		)
		for length, offset, _strLength, _strOffset in offsets:
			moFile.write(struct.pack("<2I", length, idsPoolOffset + offset))
		for _length, _offset, strLength, strOffset in offsets:
			moFile.write(struct.pack("<2I", strLength, strsPoolOffset + strOffset))
		moFile.write(ids)
		moFile.write(strs)


def _compile_mo(target, source, env) -> int:
	sourcePath = str(source[0])
	targetPath = str(target[0])
	msgfmt = shutil.which("msgfmt")
	if msgfmt:
		result = subprocess.run([msgfmt, "-o", targetPath, sourcePath], check=False)
		return result.returncode

	messages = _parse_po_messages(sourcePath)
	_write_mo(messages, targetPath)
	return 0


def generate(env):
	env.SetDefault(gettext_package_bugs_address="example@example.com")
	env.SetDefault(gettext_package_name="")
	env.SetDefault(gettext_package_version="")

	env["BUILDERS"]["gettextMoFile"] = env.Builder(
		action=Action(_compile_mo, "Compiling translation $SOURCE"),
		suffix=".mo",
		src_suffix=".po",
	)

	env["BUILDERS"]["gettextPotFile"] = env.Builder(
		action=Action("xgettext " + XGETTEXT_COMMON_ARGS, "Generating pot file $TARGET"),
		suffix=".pot",
	)

	env["BUILDERS"]["gettextMergePotFile"] = env.Builder(
		action=Action(
			"xgettext " + "--omit-header --no-location " + XGETTEXT_COMMON_ARGS,
			"Generating pot file $TARGET",
		),
		suffix=".pot",
	)
