"""

 Copyright (c) 2011 Tencent Inc.
 All rights reserved.

 Author: Huan Yu <huanyu@tencent.com>
         Feng Chen <phongchen@tencent.com>
         Yi Wang <yiwang@tencent.com>
         Chong Peng <michaelpeng@tencent.com>
 Date:   October 20, 2011

 This is the scons rules helper module which should be
 imported by Scons script

"""


import os
import shutil
import signal
import string
import subprocess
import sys
import tempfile

import SCons
import SCons.Action
import SCons.Builder
import SCons.Scanner
import SCons.Scanner.Prog

import console


# option_verbose to indicate print verbose or not
option_verbose = False


# linking tmp dir
linking_tmp_dir = ''


def generate_python_binary(target, source, env):
    setup_file = ''
    if not str(source[0]).endswith('setup.py'):
        console.warning('setup.py not existed to generate target %s, '
                'blade will generate a default one for you' % str(target[0]))
    else:
        setup_file = str(source[0])
    init_file = ''
    source_index = 2
    if not setup_file:
        source_index = 1
        init_file = str(source[0])
    else:
        init_file = str(source[1])

    init_file_dir = os.path.dirname(init_file)

    dep_source_list = []
    for s in source[source_index:]:
        dep_source_list.append(str(s))

    target_file = str(target[0])
    target_file_dir_list = target_file.split('/')
    target_profile = target_file_dir_list[0]
    target_dir = '/'.join(target_file_dir_list[0:-1])

    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    if setup_file:
        shutil.copyfile(setup_file, os.path.join(target_dir, 'setup.py'))
    else:
        target_name = os.path.basename(init_file_dir)
        if not target_name:
            console.error_exit('invalid package for target %s' % str(target[0]))
        # generate default setup.py for user
        setup_str = """
#!/usr/bin/env python
# This file was generated by blade

from setuptools import find_packages, setup


setup(
      name='%s',
      version='0.1.0',
      packages=find_packages(),
      zip_safe=True
)
""" % target_name
        default_setup_file = open(os.path.join(target_dir, 'setup.py'), 'w')
        default_setup_file.write(setup_str)
        default_setup_file.close()

    package_dir = os.path.join(target_profile, init_file_dir)
    if os.path.exists(package_dir):
        shutil.rmtree(package_dir, ignore_errors=True)

    cmd = 'cp -r %s %s' % (init_file_dir, target_dir)
    p = subprocess.Popen(
            cmd,
            env={},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            universal_newlines=True)
    std_out, std_err = p.communicate()
    if p.returncode:
        console.info(std_out)
        console.info(std_err)
        console.error_exit('failed to copy source files from %s to %s' % (
                   init_file_dir, target_dir))
        return p.returncode

    # copy file to package_dir
    for f in dep_source_list:
        dep_file_basename = os.path.basename(f)
        dep_file_dir = os.path.dirname(f)
        sub_dir = ''
        sub_dir_list = dep_file_dir.split('/')
        if len(sub_dir_list) > 1:
            sub_dir = '/'.join(dep_file_dir.split('/')[1:])
        if sub_dir:
            package_sub_dir = os.path.join(package_dir, sub_dir)
            if not os.path.exists(package_sub_dir):
                os.makedirs(package_sub_dir)
            sub_init_file = os.path.join(package_sub_dir, '__init__.py')
            if not os.path.exists(sub_init_file):
                sub_f = open(sub_init_file, 'w')
                sub_f.close()
            shutil.copyfile(f, os.path.join(package_sub_dir, dep_file_basename))

    make_egg_cmd = 'python setup.py bdist_egg'
    p = subprocess.Popen(
            make_egg_cmd,
            env={},
            cwd=target_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            universal_newlines=True)
    std_out, std_err = p.communicate()
    if p.returncode:
        console.info(std_out)
        console.info(std_err)
        console.error_exit('failed to generate python binary in %s' % target_dir)
        return p.returncode
    return 0


def generate_resource_header(target, source, env):
    res_header_path = str(target[0])

    if not os.path.exists(os.path.dirname(res_header_path)):
        os.mkdir(os.path.dirname(res_header_path))
    f = open(res_header_path, 'w')

    print >>f, '// This file was automatically generated by blade'
    print >>f, '#ifdef __cplusplus\nextern "C" {\n#endif\n'
    for s in source:
        var_name = str(s)
        for i in [',', '-', '/', '.', '+']:
            var_name = var_name.replace(i, '_')
        print >>f, 'extern const char RESOURCE_%s[%d];' % (var_name, s.get_size())
    print >>f, '\n#ifdef __cplusplus\n}\n#endif\n'
    f.close()


def generate_resource_file(target, source, env):
    src_path = str(source[0])
    new_src_path = str(target[0])
    cmd = 'xxd -i %s | sed "s/unsigned char /const char RESOURCE_/g" > %s' % (
           src_path, new_src_path)
    p = subprocess.Popen(
            cmd,
            env={},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            universal_newlines=True)
    std_out, std_err = p.communicate()
    if p.returncode:
        console.info(std_out)
        console.info(std_err)
        console.error_exit('failed to generate resource file')
    return p.returncode


def MakeAction(cmd, cmdstr):
    global option_verbose
    if option_verbose:
        return SCons.Action.Action(cmd)
    else:
        return SCons.Action.Action(cmd, cmdstr)


_ERRORS = [': error:', ': fatal error:', ': undefined reference to',
           ': cannot find ', ': ld returned 1 exit status']
_WARNINGS = [': warning:', ': note: ']


def error_colorize(message):
    colored_message = []
    for t in message.splitlines(True):
        color = 'cyan'

        # For clang column indicator, such as '^~~~~~'
        if t.strip().startswith('^'):
            color = 'green'
        else:
            for w in _WARNINGS:
                if w in t:
                    color = 'yellow'
                    break
            for w in _ERRORS:
                if w in t:
                    color = 'red'
                    break

        colored_message.append(console.colors(color))
        colored_message.append(t)
        colored_message.append(console.colors('end'))
    return ''.join(colored_message)


def echospawn(sh, escape, cmd, args, env):
    # convert env from unicode strings
    asciienv = {}
    for key, value in env.iteritems():
        asciienv[key] = str(value)

    cmdline = ' '.join(args)
    p = subprocess.Popen(
        cmdline,
        env=asciienv,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        shell=True,
        universal_newlines=True)
    (stdout, stderr) = p.communicate()

    if p.returncode:
        if p.returncode != -signal.SIGINT:
            # Error
            sys.stdout.write(error_colorize(stdout))
            sys.stderr.write(error_colorize(stderr))
    else:
        if stderr:
            # Only warnings
            sys.stdout.write(error_colorize(stdout))
            sys.stderr.write(error_colorize(stderr))
        else:
            sys.stdout.write(stdout)

    return p.returncode


def _blade_action_postfunc(closing_message):
    """To do post jobs if blade's own actions failed to build. """
    console.info(closing_message)
    # Remember to write the dblite incase of re-linking once fail to
    # build last time. We should elaborate a way to avoid rebuilding
    # after failure of our own builders or actions.
    SCons.SConsign.write()


def _fast_link_helper(target, source, env, link_com):
    """fast link helper function. """
    target_file = str(target[0])
    prefix_str = 'blade_%s' % target_file.replace('/', '_').replace('.', '_')
    fd, temporary_file = tempfile.mkstemp(suffix='xianxian',
                                          prefix=prefix_str,
                                          dir=linking_tmp_dir)
    os.close(fd)

    sources = []
    for s in source:
        sources.append(str(s))

    link_com_str = link_com.substitute(
                   FL_TARGET=temporary_file,
                   FL_SOURCE=' '.join(sources))
    p = subprocess.Popen(
                        link_com_str,
                        env=os.environ,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        shell=True,
                        universal_newlines=True)
    std_out, std_err = p.communicate()
    if std_out:
        print std_out
    if std_err:
        print std_err
    if p.returncode == 0:
        shutil.move(temporary_file, target_file)
        if not os.path.exists(target_file):
            console.warning('failed to genreate %s in link on tmpfs mode' % target_file)
    else:
        _blade_action_postfunc('failed while fast linking')
        return p.returncode


def fast_link_sharelib_action(target, source, env):
    # $SHLINK -o $TARGET $SHLINKFLAGS $__RPATH $SOURCES $_LIBDIRFLAGS $_LIBFLAGS
    link_com = string.Template('%s -o $FL_TARGET %s %s $FL_SOURCE %s %s' % (
                env.subst('$SHLINK'),
                env.subst('$SHLINKFLAGS'),
                env.subst('$__RPATH'),
                env.subst('$_LIBDIRFLAGS'),
                env.subst('$_LIBFLAGS')))
    return _fast_link_helper(target, source, env, link_com)


def fast_link_prog_action(target, source, env):
    # $LINK -o $TARGET $LINKFLAGS $__RPATH $SOURCES $_LIBDIRFLAGS $_LIBFLAGS
    link_com = string.Template('%s -o $FL_TARGET %s %s $FL_SOURCE %s %s' % (
                env.subst('$LINK'),
                env.subst('$LINKFLAGS'),
                env.subst('$__RPATH'),
                env.subst('$_LIBDIRFLAGS'),
                env.subst('$_LIBFLAGS')))
    return _fast_link_helper(target, source, env, link_com)


def create_fast_link_prog_builder(env):
    """
       This is the function to create blade fast link
       program builder. It will overwrite the program
       builder of top level env if user specifies an
       option to apply fast link method that they want
       to place the blade output to distributed file
       system to advoid the random read write of linker
       largely degrades building performance.
    """
    new_link_action = MakeAction(fast_link_prog_action, '$LINKCOMSTR')
    program = SCons.Builder.Builder(action=new_link_action,
                                    emitter='$PROGEMITTER',
                                    prefix='$PROGPREFIX',
                                    suffix='$PROGSUFFIX',
                                    src_suffix='$OBJSUFFIX',
                                    src_builder='Object',
                                    target_scanner=SCons.Scanner.Prog.ProgramScanner())
    env['BUILDERS']['Program'] = program


def create_fast_link_sharelib_builder(env):
    """
       This is the function to create blade fast link
       sharelib builder. It will overwrite the sharelib
       builder of top level env if user specifies an
       option to apply fast link method that they want
       to place the blade output to distributed file
       system to advoid the random read write of linker
       largely degrades building performance.
    """
    new_link_actions = []
    new_link_actions.append(SCons.Defaults.SharedCheck)
    new_link_actions.append(MakeAction(fast_link_sharelib_action, '$SHLINKCOMSTR'))

    sharedlib = SCons.Builder.Builder(action=new_link_actions,
                                      emitter='$SHLIBEMITTER',
                                      prefix='$SHLIBPREFIX',
                                      suffix='$SHLIBSUFFIX',
                                      target_scanner=SCons.Scanner.Prog.ProgramScanner(),
                                      src_suffix='$SHOBJSUFFIX',
                                      src_builder='SharedObject')
    env['BUILDERS']['SharedLibrary'] = sharedlib


def create_fast_link_builders(env):
    """Creates fast link builders - Program and  SharedLibrary. """
    # Check requirement
    acquire_temp_place = "df | grep tmpfs | awk '{print $5, $6}'"
    p = subprocess.Popen(
                        acquire_temp_place,
                        env=os.environ,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        shell=True,
                        universal_newlines=True)
    std_out, std_err = p.communicate()

    # Do not try to overwrite builder with error
    if p.returncode:
        console.warning('you have link on tmp enabled, but it is not fullfilled to make it.')
        return

    # No tmpfs to do fastlink, will not overwrite the builder
    if not std_out:
        console.warning('you have link on tmp enabled, but there is no tmpfs to make it.')
        return

    # Use the first one
    global linking_tmp_dir
    usage, linking_tmp_dir = tuple(std_out.splitlines(False)[0].split())

    # Do not try to do that if there is no memory space left
    usage = int(usage.replace('%', ''))
    if usage > 90:
        console.warning('you have link on tmp enabled, '
                'but there is not enough space on %s to make it.' % linking_tmp_dir)
        return

    console.info('building in link on tmpfs mode')

    create_fast_link_sharelib_builder(env)
    create_fast_link_prog_builder(env)
