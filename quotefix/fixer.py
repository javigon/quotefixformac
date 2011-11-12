from    AppKit                  import *
from    quotefix.utils          import swizzle
from    quotefix.attribution    import CustomizedAttribution
from    quotefix.messagetypes   import *
from    objc                    import Category, lookUpClass
import  logging, re, traceback

# our own MailDocumentEditor implementation
MailDocumentEditor = lookUpClass('MailDocumentEditor')
class MailDocumentEditor(Category(MailDocumentEditor)):

    @classmethod
    def registerQuoteFixApplication(cls, app):
        cls.app = app

    @swizzle(MailDocumentEditor, 'finishLoadingEditor')
    def finishLoadingEditor(self, original):
        logging.debug('MailDocumentEditor finishLoadingEditor')

        # execute original finishLoadingEditor()
        original(self)

        try:
            # check if we can proceed
            if not self.app.is_active:
                logging.debug("QuoteFix is not active, so no QuoteFixing for you!")
                return

            # check for supported messagetype
            logging.debug('message type is %s' % self.messageType())
            if self.messageType() not in self.app.message_types_to_quotefix:
                logging.debug('\t not in %s, bailing' % self.app.message_types_to_quotefix)
                return

            # grab composeView instance (this is the WebView which contains the
            # message editor) and check for the right conditions
            try:
                view = objc.getInstanceVariable(self, 'composeWebView')
            except:
                # was renamed in Lion
                view = objc.getInstanceVariable(self, '_composeWebView')

            # grab some other variables we need to perform our business
            backend     = self.backEnd()
            htmldom     = view.mainFrame().DOMDocument()
            htmlroot    = htmldom.documentElement()

            # send original HTML to menu for debugging
            self.app.html = htmlroot.innerHTML()

            # should we be quotefixing?
            if not self.app.is_quotefixing:
                logging.debug('quotefixing turned off in preferences, skipping that part')
            else:
                # move cursor to end of document
                view.moveToEndOfDocument_(self)

                # remove quotes?
                if self.app.remove_quotes:
                    logging.debug('calling remove_quotes()')
                    self.remove_quotes(htmldom, self.app.remove_quotes_level)
                    backend.setHasChanges_(False)

                # make quotes selectable?
                if self.app.selectable_quotes:
                    logging.debug('calling make_selectable_quotes()')
                    self.make_selectable_quotes(view, htmldom)
                    backend.setHasChanges_(False)

                # remove signature from sender
                if not self.app.keep_sender_signature:
                    logging.debug('calling remove_old_signature()')
                    if self.remove_old_signature(htmldom, view):
                        backend.setHasChanges_(False)

                # place cursor above own signature (if any)
                logging.debug('calling move_above_new_signature()')
                if self.move_above_new_signature(htmldom, view):
                    backend.setHasChanges_(False)
                else:
                    view.insertNewline_(self)

                # perform some general cleanups
                logging.debug('calling cleanup_layout()')
                if self.cleanup_layout(htmlroot):
                    backend.setHasChanges_(False)

            # provide custom attribution?
            attributor = None
            if self.app.use_custom_reply_attribution and self.messageType() in [ REPLY, REPLY_ALL ]:
                logging.debug("calling customize_attribution() for reply(-all)")
                attributor = CustomizedAttribution.customize_reply
            elif self.app.use_custom_forwarding_attribution and self.messageType() == FORWARD:
                logging.debug("calling customize_attribution() for forwarding")
                attributor = CustomizedAttribution.customize_forward

            if attributor:
                # play nice with Attachment Tamer
                try:
                    message = backend.draftMessage()
                except:
                    message = backend._makeMessageWithContents_isDraft_shouldSign_shouldEncrypt_shouldSkipSignature_shouldBePlainText_(
                        backend.copyOfContentsForDraft_shouldBePlainText_isOkayToForceRichText_(True, False, True),
                        True,
                        False,
                        False,
                        False,
                        False
                    )
                try:
                    attributor(
                        app         = self.app,
                        editor      = self,
                        dom         = htmldom,
                        reply       = message,
                        inreplyto   = backend.originalMessage()
                    )
                except:
                    # ignore when not debugging
                    if self.app.is_debugging:
                        raise

            # move to beginning of line
            logging.debug('calling view.moveToBeginningOfLine()')
            view.moveToBeginningOfLine_(self)

            # done
            logging.debug('QuoteFixing done')
        except Exception, e:
            logging.exception(e)
            if self.app.is_debugging:
                NSRunAlertPanel(
                    'QuoteFix caught an exception',
                    'The QuoteFix plug-in caught an exception:\n\n' +
                    traceback.format_exc() +
                    '\nPlease contact the developer quoting the contents of this alert.',
                    None, None, None
                )

    def remove_quotes(self, dom, level):
        # find all blockquotes
        blockquotes = dom.querySelectorAll_("blockquote")
        for i in range(blockquotes.length()):
            blockquote = blockquotes.item_(i)
            # check quotelevel against maximum allowed level
            if blockquote.quoteLevel() >= level:
                blockquote.parentNode().removeChild_(blockquote)

    def make_selectable_quotes(self, view, dom):
        return

        # find all blockquotes
        blockquotes = dom.querySelectorAll_("blockquote")
        for i in range(blockquotes.length()):
            blockquote = blockquotes.item_(i)
            # don't fix top-level blockquote
            if blockquote.quoteLevel() > 1:
#                # get parent node
#                parent = blockquote.parentNode()
#
#                # check for DIV
#                if isinstance(parent, DOMElement) and parent.nodeName().lower() == 'div':
#                    # replace parent-container with a new (selectable) BLOCKQUOTE
#                    newblockquote = dom.createElement_("blockquote")
#                    newblockquote.setAttribute_value_("style", "background:rgba(255,255,255,0.1);padding:0!important;margin:0!important;z-index:%d" % (blockquote.quoteLevel() * 10))
#                    newblockquote.setInnerHTML_(parent.innerHTML())
#                    grandparent = parent.parentNode()
#                    grandparent.replaceChild_oldChild_(newblockquote, parent)
#                continue

                # get current computed style
                style = dom.getComputedStyle_pseudoElement_(blockquote, None).cssText()

                # remove text-color-related stuff (so it will be inherited)
                style = re.sub(r'\scolor.*?:.*?;', '', style)
                style = re.sub(r'\soutline-color.*?:.*?;', '', style)
                style = re.sub(r'\s-webkit-text-emphasis-color.*?:.*?;', '', style)
                style = re.sub(r'\s-webkit-text-fill-color.*?:.*?;', '', style)
                style = re.sub(r'\s-webkit-text-stroke-color.*?:.*?;', '', style)
                style = re.sub(r'\sflood-color.*?:.*?;', '', style)
                style = re.sub(r'\slighting-color.*?:.*?;', '', style)

                # remove 'type' attribute
                blockquote.removeAttribute_("type")

                # and set style attribute to match original style
                blockquote.setAttribute_value_("style", style)

    # try to find, and remove, signature of sender
    def remove_old_signature(self, dom, view):
        signature   = None
        root        = dom.documentElement()

        # grab first blockquote (if any)
        blockquote = root.firstDescendantBlockQuote()
        if not blockquote:
            return False

        # get matcher
        matcher = self.app.signature_matcher

        # find nodes which might contain senders signature
        possibles = [
            #"body > div > blockquote > div > br",
            #"body > div > blockquote br",
            #"body > blockquote br",
            #"body > blockquote > div",
            "div", "br"
        ]

        nodes = []
        for possible in possibles:
            matches = dom.querySelectorAll_(possible)
            nodes += [ matches.item_(i) for i in range(matches.length()) ]

        # try to find a signature
        for node in nodes:
            # skip nodes which aren't at quotelevel 1
            if node.quoteLevel() != 1:
                continue

#            if node.nodeName().lower() == 'div':
#                NSLog("div: %r" % unicode( node.innerHTML() ))
#            elif node.nodeName().lower() == 'br':
#                nextnode = node.nextSibling()
#                if isinstance(nextnode, DOMText):
#                    NSLog("br, nextnode = text: %r" % unicode( nextnode.data() ))
#                else:
#                    NSLog("br, nextnode: %r" % unicode( nextnode) )

            # BR's are empty, so treat them differently
            if node.nodeName().lower() == 'br':
                nextnode = node.nextSibling()
                if isinstance(nextnode, DOMText) and matcher.search(nextnode.data()):
                    signature = node
                    break
            elif node.nodeName().lower() == 'div' and matcher.search(node.innerHTML()):
                signature = node
                break

        # if we found a signature, remove it
        if signature:
            # remove all siblings following signature, except for attachments
            node    = signature
            parent  = signature.parentNode()
            while node:
                if node.nodeName().lower() == 'object':
                    node = node.nextSibling()
                else:
                    nextnode = node.nextSibling()
                    parent.removeChild_(node)
                    node = nextnode
                while not node and parent != blockquote:
                    node    = parent.nextSibling()
                    parent  = parent.parentNode()

            # move down a line
            view.moveDown_(self)

            # and insert a paragraph break
            view.insertParagraphSeparator_(self)

            # remove empty lines
            blockquote.removeStrayLinefeeds()

            # signal that we removed an old signature
            return True

        # found nothing?
        return False

    def move_above_new_signature(self, dom, view):
        # find new signature by ID
        div = dom.getElementById_("AppleMailSignature")
        if not div:
            return False

        # set selection range
        domrange = dom.createRange()
        domrange.selectNode_(div)

        # create selection
        view.setSelectedDOMRange_affinity_(domrange, 0)

        # move up (positions cursor above signature)
        view.moveUp_(self)

        # insert a paragraph break?
        if not self.app.no_whitespace_below_quote:
            view.insertParagraphSeparator_(self)

        # signal that we moved
        return True

    def cleanup_layout(self, root):
        # clean up stray linefeeds
        if not self.app.keep_leading_whitespace:
            root.getElementsByTagName_("body").item_(0)._removeStrayLinefeedsAtBeginning()

        # remove trailing whitespace on first blockquote?
        if self.app.remove_trailing_whitespace:
            blockquote = root.firstDescendantBlockQuote()
            if blockquote:
                blockquote._removeStrayLinefeedsAtEnd()

        # done?
        if self.app.keep_attribution_whitespace:
            return True

        # clean up linebreaks before first blockquote
        blockquote = root.firstDescendantBlockQuote()
        if blockquote:
            parent  = blockquote.parentNode()
            node    = blockquote.previousSibling()
            while node and node.nodeName().lower() == 'br':
                parent.removeChild_(node)
                node = blockquote.previousSibling()

        return True
